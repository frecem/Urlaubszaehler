/*!
 * Urlaubszähler-Karte für Home Assistant
 * ---------------------------------------
 * Zeigt alle geplanten Urlaube der Integration "urlaubszaehler" als kompakte
 * Liste und zeichnet darüber eine Weltkarte mit gestrichelten Reisebögen vom
 * Standort des Home-Assistant-Servers zu den Reisezielen.
 *
 * Der Kartenausschnitt richtet sich automatisch nach dem Zuhause und allen
 * Zielen. Mehrere Reisen zum selben Ort laufen nebeneinander statt übereinander.
 *
 * Kartendaten: Natural Earth (public domain), vereinfacht und delta-kodiert.
 */

const KARTEN_VERSION = "1.0.1";

/** Pfad des mitgelieferten Blueprints im Konfigurationsverzeichnis. */
const BLUEPRINT_PFAD = "urlaubszaehler/urlaub_anlegen.yaml";

/* --------------------------------------------------------------------------
 * Weltkarte: Dekodierung der eingebetteten Umrisse
 * ------------------------------------------------------------------------ */

const WELT_KODIERT = "__WORLD__";
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

const ZEICHENWERT = (() => {
  const tabelle = new Int8Array(128).fill(-1);
  for (let i = 0; i < ALPHABET.length; i++) tabelle[ALPHABET.charCodeAt(i)] = i;
  return tabelle;
})();

/** Dekodiert die Umrisse zu Ringen aus [lon, lat, …] inklusive Bounding-Box. */
function weltDekodieren(text) {
  const ringe = [];
  for (const teil of text.split("|")) {
    const punkte = [];
    let i = 0;
    let x = 0;
    let y = 0;
    let minLon = Infinity;
    let maxLon = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;
    while (i < teil.length) {
      for (let achse = 0; achse < 2; achse++) {
        let wert = 0;
        let schub = 0;
        let zeichen;
        do {
          zeichen = ZEICHENWERT[teil.charCodeAt(i++)];
          wert |= (zeichen & 31) << schub;
          schub += 5;
        } while (zeichen & 32);
        const delta = (wert >>> 1) ^ -(wert & 1);
        if (achse === 0) x += delta;
        else y += delta;
      }
      const lon = x / 100;
      const lat = y / 100;
      punkte.push(lon, lat);
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
    ringe.push({ punkte, minLon, maxLon, minLat, maxLat });
  }
  return ringe;
}

let WELT = null;
function welt() {
  if (WELT === null) WELT = weltDekodieren(WELT_KODIERT);
  return WELT;
}

/* --------------------------------------------------------------------------
 * Projektion (Web-Mercator)
 * ------------------------------------------------------------------------ */

const MAX_LAT = 85;

function mercator(lat) {
  const begrenzt = Math.max(-MAX_LAT, Math.min(MAX_LAT, lat));
  return Math.log(Math.tan(Math.PI / 4 + (begrenzt * Math.PI) / 360));
}

/**
 * Ermittelt den Kartenausschnitt so, dass Zuhause und alle Ziele hineinpassen,
 * ohne die Karte zu verzerren.
 */
function ausschnittBerechnen(punkte, breite, hoehe) {
  let minLon = Infinity;
  let maxLon = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of punkte) {
    const y = mercator(p.lat);
    if (p.lon < minLon) minLon = p.lon;
    if (p.lon > maxLon) maxLon = p.lon;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }

  // Mindestausdehnung. Die Umrisse sind bewusst grob (Übersichtskarte);
  // bei einer kurzen Reise würde ein enger Ausschnitt sie zu Klötzchen
  // vergrößern. 18 Grad zeigen bei einer Reise innerhalb Europas noch
  // erkennbare Länder.
  const MIN_SPANNE = 18;
  let spanneLon = Math.max(maxLon - minLon, MIN_SPANNE);
  let spanneY = Math.max(maxY - minY, (MIN_SPANNE * Math.PI) / 180);

  // Rand, damit Punkte und Beschriftungen nicht am Rand kleben.
  spanneLon *= 1.18;
  spanneY *= 1.22;

  const mitteLon = (minLon + maxLon) / 2;
  const mitteY = (minY + maxY) / 2;

  // Seitenverhältnis angleichen: die kleinere Richtung wird aufgeweitet.
  const zielVerhaeltnis = breite / hoehe;
  const lonInY = (spanneLon * Math.PI) / 180;
  if (lonInY / spanneY > zielVerhaeltnis) {
    spanneY = lonInY / zielVerhaeltnis;
  } else {
    spanneLon = ((spanneY * zielVerhaeltnis) * 180) / Math.PI;
  }

  return {
    minLon: mitteLon - spanneLon / 2,
    maxLon: mitteLon + spanneLon / 2,
    minY: mitteY - spanneY / 2,
    maxY: mitteY + spanneY / 2,
    breite,
    hoehe,
  };
}

function projizieren(ausschnitt, lon, lat) {
  const { minLon, maxLon, minY, maxY, breite, hoehe } = ausschnitt;
  return [
    ((lon - minLon) / (maxLon - minLon)) * breite,
    ((maxY - mercator(lat)) / (maxY - minY)) * hoehe,
  ];
}

/* --------------------------------------------------------------------------
 * Hilfsfunktionen
 * ------------------------------------------------------------------------ */

const FARBEN = [210, 14, 150, 276, 36, 330, 190, 96];

function farbe(index) {
  return `hsl(${FARBEN[index % FARBEN.length]}, 62%, 52%)`;
}

/** Verbleibende Zeit; stoppt bei 0 und rechnet nicht negativ weiter. */
function restzeit(zielZeitstempel, jetzt) {
  const rest = Math.max(0, zielZeitstempel - jetzt / 1000);
  return {
    sekunden: rest,
    tage: Math.floor(rest / 86400),
    stunden: Math.floor((rest % 86400) / 3600),
    minuten: Math.floor((rest % 3600) / 60),
  };
}

function escapeHtml(text) {
  return String(text ?? "").replace(
    /[&<>"']/g,
    (z) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[z],
  );
}

/* --------------------------------------------------------------------------
 * Die Karte
 * ------------------------------------------------------------------------ */

class UrlaubszaehlerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._urlaube = [];
    this._signatur = "";
    this._kartenbreite = 0;
    this._takt = null;
    this._beobachter = null;
    this._geraete = null;
  }

  static getStubConfig() {
    return { title: "Urlaubszähler", show_map: true, map_height: 260 };
  }

  static getConfigElement() {
    return document.createElement("urlaubszaehler-card-editor");
  }

  setConfig(config) {
    this._config = {
      title: "Urlaubszähler",
      show_map: true,
      map_height: 260,
      max: 0,
      show_add: true,
      blueprint_path: BLUEPRINT_PFAD,
      ...config,
    };
    this._signatur = "";
    this._aufbauen();
  }

  /** Größe in einer Abschnitts-Ansicht (Sections). */
  getGridOptions() {
    const zeilen = 2 + (this._config.show_map ? 4 : 0) + (this._config.show_add ? 1 : 0);
    return {
      columns: "full",
      min_columns: 6,
      rows: zeilen + Math.max(1, this._urlaube.length) * 2,
      min_rows: 4,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._urlaubeLesen();
    this._zeichnen();
  }

  getCardSize() {
    return (this._config.show_map ? 4 : 1) + Math.max(1, this._urlaube.length);
  }

  connectedCallback() {
    // Eigener Takt, damit die Minutenanzeige stimmt, auch wenn gerade keine
    // Zustandsänderung vom Server kommt.
    this._takt = window.setInterval(() => this._countdownAktualisieren(), 15000);
    this._breiteBeobachten();
  }

  disconnectedCallback() {
    if (this._takt) window.clearInterval(this._takt);
    this._takt = null;
    if (this._beobachter) this._beobachter.disconnect();
    this._beobachter = null;
  }

  /* ---------------------------------------------------------------- Daten */

  _urlaubeLesen() {
    const zustaende = this._hass?.states ?? {};
    let ids = this._config.entities;
    if (!ids || !ids.length) {
      ids = Object.keys(zustaende).filter(
        (id) =>
          id.startsWith("sensor.") &&
          zustaende[id].attributes &&
          zustaende[id].attributes.urlaub_id !== undefined,
      );
    }

    const urlaube = [];
    for (const id of ids) {
      const zustand = zustaende[id];
      if (!zustand) continue;
      const a = zustand.attributes;
      const zeitstempel = Number(a.start_zeitstempel ?? zustand.state);
      if (!Number.isFinite(zeitstempel)) continue;
      urlaube.push({
        entity_id: id,
        zeitstempel,
        ziel: a.ziel ?? "",
        wer: a.wer ?? "",
        lat: typeof a.breitengrad === "number" ? a.breitengrad : null,
        lon: typeof a.laengengrad === "number" ? a.laengengrad : null,
      });
    }

    urlaube.sort((a, b) => a.zeitstempel - b.zeitstempel);
    this._urlaube =
      this._config.max > 0 ? urlaube.slice(0, this._config.max) : urlaube;
  }

  /* ---------------------------------------------------------------- Aufbau */

  _aufbauen() {
    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          overflow: hidden;
          --uz-abstand: 16px;
        }
        .kopf {
          font-size: var(--ha-card-header-font-size, 24px);
          font-weight: var(--ha-card-header-font-weight, 400);
          color: var(--ha-card-header-color, var(--primary-text-color));
          padding: var(--uz-abstand) var(--uz-abstand) 8px;
          line-height: 1.2;
        }
        .karte {
          position: relative;
          width: 100%;
          background: var(--uz-meer, transparent);
        }
        .karte svg { display: block; width: 100%; }
        .leer {
          padding: 8px var(--uz-abstand) var(--uz-abstand);
          color: var(--secondary-text-color);
        }
        .liste { padding: 4px 0 4px; }
        .zeile {
          display: grid;
          grid-template-columns: 10px 1fr auto;
          grid-template-areas:
            "punkt ziel  count"
            "punkt wer   ab";
          gap: 0 12px;
          align-items: center;
          padding: 10px var(--uz-abstand);
          cursor: pointer;
          border-top: 1px solid var(--divider-color);
        }
        .zeile:hover { background: var(--secondary-background-color); }
        .punkt {
          grid-area: punkt;
          width: 10px; height: 10px;
          border-radius: 50%;
          align-self: center;
        }
        .ziel {
          grid-area: ziel;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .wer {
          grid-area: wer;
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .count {
          grid-area: count;
          text-align: right;
          white-space: nowrap;
          color: var(--primary-text-color);
          font-variant-numeric: tabular-nums;
        }
        .count b { font-size: 1.15em; font-weight: 600; }
        .ab {
          grid-area: ab;
          text-align: right;
          white-space: nowrap;
          font-size: 0.85em;
          color: var(--secondary-text-color);
          font-variant-numeric: tabular-nums;
        }
        .hinweis {
          grid-area: ab;
          text-align: right;
          font-size: 0.8em;
          color: var(--warning-color, #ffa726);
        }
        .land { fill: currentColor; fill-opacity: 0.10; stroke: currentColor;
                stroke-opacity: 0.22; stroke-width: 0.6; }
        .bogen { fill: none; stroke-linecap: round; }
        .beschriftung {
          font-size: 11px;
          fill: var(--primary-text-color);
          paint-order: stroke;
          stroke: var(--card-background-color, var(--ha-card-background, #fff));
          stroke-width: 3px;
          stroke-linejoin: round;
        }
        .fuss { padding: 4px var(--uz-abstand) var(--uz-abstand); }
        .fuss:empty { display: none; }
        .knopf {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          border: none;
          border-radius: 999px;
          padding: 10px 20px;
          font: inherit;
          font-weight: 500;
          cursor: pointer;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        .knopf:hover { filter: brightness(1.1); }
        .knopf:disabled { opacity: 0.6; cursor: default; }
        .knopf.leise {
          background: transparent;
          color: var(--primary-color);
          padding: 10px 12px;
        }
        .dialog-huelle {
          position: fixed;
          inset: 0;
          z-index: 9;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 16px;
          background: rgba(0, 0, 0, 0.5);
        }
        .dialog-huelle[hidden] { display: none; }
        .dialog {
          width: min(460px, 100%);
          max-height: 90vh;
          overflow-y: auto;
          border-radius: 16px;
          padding: 20px;
          background: var(--card-background-color, var(--ha-card-background, #fff));
          color: var(--primary-text-color);
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        .dialog h2 { margin: 0 0 4px; font-size: 1.3em; font-weight: 500; }
        .dialog p.hinweis {
          margin: 0 0 16px;
          color: var(--secondary-text-color);
          font-size: 0.9em;
        }
        .feld { margin-bottom: 16px; }
        .feld > label.titel {
          display: block;
          margin-bottom: 6px;
          font-weight: 500;
        }
        .feld input[type="text"],
        .feld input[type="date"],
        .feld input[type="time"] {
          width: 100%;
          box-sizing: border-box;
          padding: 10px;
          font: inherit;
          color: var(--primary-text-color);
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 8px;
        }
        .zeitzeile { display: flex; gap: 10px; }
        .zeitzeile > * { flex: 1; }
        .auswahl {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .auswahl label {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 7px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          cursor: pointer;
        }
        .auswahl label:has(input:checked) {
          border-color: var(--primary-color);
          background: color-mix(in srgb, var(--primary-color) 14%, transparent);
        }
        .auswahl.leer {
          color: var(--secondary-text-color);
          font-size: 0.9em;
        }
        .fehler {
          margin: 0 0 12px;
          padding: 10px 12px;
          border-radius: 8px;
          background: color-mix(in srgb, var(--error-color, #db4437) 16%, transparent);
          color: var(--error-color, #db4437);
          font-size: 0.9em;
        }
        .dialog-knoepfe {
          display: flex;
          justify-content: flex-end;
          gap: 8px;
          margin-top: 4px;
        }
        @media (max-width: 460px) {
          .zeile {
            grid-template-columns: 10px 1fr;
            grid-template-areas: "punkt ziel" "punkt wer" ". count" ". ab";
          }
          .count, .ab, .hinweis { text-align: left; }
        }
      </style>
      <ha-card>
        <div class="kopf"></div>
        <div class="karte"></div>
        <div class="liste"></div>
        <div class="fuss"></div>
      </ha-card>
      <div class="dialog-huelle" hidden>
        <div class="dialog" role="dialog" aria-modal="true"
             aria-label="Neuen Urlaub anlegen"></div>
      </div>
    `;
    this._kopfEl = this.shadowRoot.querySelector(".kopf");
    this._kartenEl = this.shadowRoot.querySelector(".karte");
    this._listenEl = this.shadowRoot.querySelector(".liste");
    this._fussEl = this.shadowRoot.querySelector(".fuss");
    this._huelleEl = this.shadowRoot.querySelector(".dialog-huelle");
    this._dialogEl = this.shadowRoot.querySelector(".dialog");
    this._huelleEl.addEventListener("click", (e) => {
      if (e.target === this._huelleEl) this._dialogSchliessen();
    });
    // Der Beobachter hing am alten, nun ersetzten Element.
    if (this._beobachter) {
      this._beobachter.disconnect();
      this._beobachter = null;
    }
    this._breiteBeobachten();
  }

  _breiteBeobachten() {
    if (!this._kartenEl || this._beobachter || !window.ResizeObserver) return;
    this._beobachter = new ResizeObserver((eintraege) => {
      const breite = Math.round(eintraege[0].contentRect.width);
      if (breite && Math.abs(breite - this._kartenbreite) > 4) {
        this._kartenbreite = breite;
        this._signatur = "";
        this._zeichnen();
      }
    });
    this._beobachter.observe(this._kartenEl);
  }

  /* -------------------------------------------------------------- Zeichnen */

  _zeichnen() {
    if (!this._kopfEl || !this._hass) return;

    this._kopfEl.textContent = this._config.title ?? "";
    this._kopfEl.style.display = this._config.title ? "" : "none";

    const signatur = JSON.stringify([
      this._urlaube.map((u) => [u.entity_id, u.zeitstempel, u.ziel, u.wer, u.lat, u.lon]),
      this._kartenbreite,
      this._config.show_map,
      this._config.map_height,
    ]);
    if (signatur === this._signatur) {
      this._countdownAktualisieren();
      return;
    }
    this._signatur = signatur;

    this._karteZeichnen();
    this._listeZeichnen();
    this._fussZeichnen();
    this._countdownAktualisieren();
  }

  _karteZeichnen() {
    const breite = this._kartenbreite;
    const hoehe = Number(this._config.map_height) || 260;
    const mitOrt = this._urlaube.filter((u) => u.lat !== null && u.lon !== null);

    if (!this._config.show_map || !breite || !mitOrt.length) {
      this._kartenEl.innerHTML = "";
      return;
    }

    const zuhause = {
      lat: this._hass.config?.latitude ?? 0,
      lon: this._hass.config?.longitude ?? 0,
    };
    const ausschnitt = ausschnittBerechnen(
      [zuhause, ...mitOrt.map((u) => ({ lat: u.lat, lon: u.lon }))],
      breite,
      hoehe,
    );

    // Dezente Fläche als Kartengrund.
    const teile = [
      `<rect x="0" y="0" width="${breite}" height="${hoehe}" ` +
        `fill="currentColor" fill-opacity="0.035"/>`,
    ];

    // Landflächen - nur was im Ausschnitt liegt.
    const minLat = (Math.atan(Math.exp(ausschnitt.minY)) * 360) / Math.PI - 90;
    const maxLat = (Math.atan(Math.exp(ausschnitt.maxY)) * 360) / Math.PI - 90;
    for (const ring of welt()) {
      if (
        ring.maxLon < ausschnitt.minLon ||
        ring.minLon > ausschnitt.maxLon ||
        ring.maxLat < minLat ||
        ring.minLat > maxLat
      ) {
        continue;
      }
      const p = ring.punkte;
      let d = "";
      for (let i = 0; i < p.length; i += 2) {
        const [x, y] = projizieren(ausschnitt, p[i], p[i + 1]);
        d += `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
      }
      teile.push(`<path class="land" d="${d}Z"/>`);
    }

    const [hx, hy] = projizieren(ausschnitt, zuhause.lon, zuhause.lat);

    // Mehrfach angesteuerte Ziele erhalten unterschiedlich starke Bögen,
    // damit sie nebeneinander statt übereinander liegen.
    const zaehler = new Map();
    mitOrt.forEach((urlaub) => {
      const schluessel = `${urlaub.lat.toFixed(2)},${urlaub.lon.toFixed(2)}`;
      const nummer = zaehler.get(schluessel) ?? 0;
      zaehler.set(schluessel, nummer + 1);
      urlaub._bogen = nummer;
      urlaub._ziel = schluessel;
    });

    const beschriftungen = new Map();
    mitOrt.forEach((urlaub) => {
      const index = this._urlaube.indexOf(urlaub);
      const [zx, zy] = projizieren(ausschnitt, urlaub.lon, urlaub.lat);
      const dx = zx - hx;
      const dy = zy - hy;
      const laenge = Math.hypot(dx, dy) || 1;
      // Senkrechte zur Verbindungslinie, immer nach oben zeigend.
      let nx = -dy / laenge;
      let ny = dx / laenge;
      if (ny > 0) {
        nx = -nx;
        ny = -ny;
      }
      const woelbung = 0.16 + urlaub._bogen * 0.15;
      const cx = (hx + zx) / 2 + nx * laenge * woelbung;
      const cy = (hy + zy) / 2 + ny * laenge * woelbung;
      teile.push(
        `<path class="bogen" d="M${hx.toFixed(1)} ${hy.toFixed(1)} ` +
          `Q${cx.toFixed(1)} ${cy.toFixed(1)} ${zx.toFixed(1)} ${zy.toFixed(1)}" ` +
          `stroke="${farbe(index)}" stroke-width="1.6" stroke-opacity="0.5" ` +
          `stroke-dasharray="5 5"/>`,
      );
      teile.push(
        `<circle cx="${zx.toFixed(1)}" cy="${zy.toFixed(1)}" r="4.5" ` +
          `fill="${farbe(index)}" fill-opacity="0.9"/>`,
      );
      if (!beschriftungen.has(urlaub._ziel)) {
        beschriftungen.set(urlaub._ziel, { x: zx, y: zy, text: urlaub.ziel });
      }
    });

    // Zuhause
    teile.push(
      `<circle cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="7" ` +
        `fill="none" stroke="var(--secondary-text-color)" stroke-opacity="0.5" ` +
        `stroke-width="1.2"/>`,
      `<circle cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="3.2" ` +
        `fill="var(--secondary-text-color)"/>`,
    );

    // Beschriftungen setzen und dabei Überlappungen nach unten ausweichen.
    const gesetzt = [];
    for (const { x, y, text } of [...beschriftungen.values()].sort(
      (a, b) => a.y - b.y,
    )) {
      const rechts = x < breite * 0.72;
      const bx = x + (rechts ? 9 : -9);
      let by = y + 4;
      let versuche = 0;
      while (
        versuche++ < 6 &&
        gesetzt.some((g) => Math.abs(g.x - bx) < 80 && Math.abs(g.y - by) < 13)
      ) {
        by += 13;
      }
      gesetzt.push({ x: bx, y: by });
      teile.push(
        `<text class="beschriftung" x="${bx.toFixed(1)}" y="${by.toFixed(1)}" ` +
          `text-anchor="${rechts ? "start" : "end"}">${escapeHtml(text)}</text>`,
      );
    }

    this._kartenEl.innerHTML =
      `<svg viewBox="0 0 ${breite} ${hoehe}" width="${breite}" height="${hoehe}" ` +
      `style="color: var(--primary-text-color)" role="img" ` +
      `aria-label="Weltkarte mit den Reisezielen">${teile.join("")}</svg>`;
  }

  _listeZeichnen() {
    if (!this._urlaube.length) {
      this._listenEl.innerHTML =
        `<div class="leer">Aktuell ist kein Urlaub geplant.</div>`;
      return;
    }

    this._listenEl.innerHTML = this._urlaube
      .map((urlaub, index) => {
        const ohneOrt = urlaub.lat === null || urlaub.lon === null;
        return `
          <div class="zeile" data-entity="${escapeHtml(urlaub.entity_id)}">
            <span class="punkt" style="background:${farbe(index)}"></span>
            <span class="ziel">${escapeHtml(urlaub.ziel)}</span>
            <span class="wer">${escapeHtml(urlaub.wer)}</span>
            <span class="count" data-count="${index}"></span>
            ${
              ohneOrt
                ? `<span class="hinweis">Ort nicht gefunden</span>`
                : `<span class="ab">${escapeHtml(this._zeitpunkt(urlaub.zeitstempel))}</span>`
            }
          </div>`;
      })
      .join("");

    this._listenEl.querySelectorAll(".zeile").forEach((zeile) => {
      zeile.addEventListener("click", () => {
        this.dispatchEvent(
          new CustomEvent("hass-more-info", {
            detail: { entityId: zeile.dataset.entity },
            bubbles: true,
            composed: true,
          }),
        );
      });
    });
  }

  /* ------------------------------------------------- Urlaub anlegen */

  _fussZeichnen() {
    // Automatisierungen anlegen darf nur ein Administrator.
    const erlaubt = this._config.show_add && this._hass?.user?.is_admin !== false;
    if (!erlaubt) {
      this._fussEl.innerHTML = "";
      return;
    }
    this._fussEl.innerHTML =
      `<button class="knopf" type="button">＋ Urlaub anlegen</button>`;
    this._fussEl.querySelector("button").addEventListener("click", () =>
      this._dialogOeffnen(),
    );
  }

  /** Alle Teilnehmer-Entitäten des Urlaubszählers. */
  _teilnehmer() {
    const zustaende = this._hass?.states ?? {};
    return Object.keys(zustaende)
      .filter(
        (id) =>
          id.startsWith("binary_sensor.") &&
          zustaende[id].attributes?.anzeigename !== undefined,
      )
      .map((id) => ({ id, name: zustaende[id].attributes.anzeigename }))
      .sort((a, b) => a.name.localeCompare(b.name, "de"));
  }

  /** Geräte mit der Home-Assistant-App (einmal je Sitzung geladen). */
  async _geraeteLaden() {
    if (this._geraete) return this._geraete;
    try {
      const alle = await this._hass.callWS({ type: "config/device_registry/list" });
      this._geraete = alle
        .filter((g) => (g.identifiers || []).some((i) => i[0] === "mobile_app"))
        .map((g) => ({ id: g.id, name: g.name_by_user || g.name }))
        .sort((a, b) => (a.name || "").localeCompare(b.name || "", "de"));
    } catch (fehler) {
      this._geraete = [];
    }
    return this._geraete;
  }

  async _dialogOeffnen() {
    const geraete = await this._geraeteLaden();
    const teilnehmer = this._teilnehmer();

    // Vorschlag: morgen, 08:00 Uhr.
    const morgen = new Date(Date.now() + 86400000);
    const datum = morgen.toISOString().slice(0, 10);

    const liste = (eintraege, name, leerText) =>
      eintraege.length
        ? `<div class="auswahl">${eintraege
            .map(
              (e) =>
                `<label><input type="checkbox" name="${name}" ` +
                `value="${escapeHtml(e.id)}">${escapeHtml(e.name)}</label>`,
            )
            .join("")}</div>`
        : `<div class="auswahl leer">${leerText}</div>`;

    this._dialogEl.innerHTML = `
      <h2>Neuen Urlaub anlegen</h2>
      <p class="hinweis">Es wird eine Automatisierung aus dem Blueprint
        erstellt – mit Countdown-Sensor und Push-Erinnerungen.</p>
      <div class="fehler" hidden></div>
      <div class="feld">
        <label class="titel">Wer fährt in den Urlaub?</label>
        ${liste(teilnehmer, "teilnehmer",
          "Keine Personen angelegt – bitte zuerst den Urlaubszähler einrichten.")}
      </div>
      <div class="feld">
        <label class="titel" for="uz-ziel">Wohin geht die Reise?</label>
        <input type="text" id="uz-ziel" placeholder="z. B. Gardasee">
      </div>
      <div class="feld">
        <label class="titel">Wann geht es los?</label>
        <div class="zeitzeile">
          <input type="date" id="uz-datum" value="${datum}">
          <input type="time" id="uz-zeit" value="08:00">
        </div>
      </div>
      <div class="feld">
        <label class="titel">Erinnerungen an diese Geräte</label>
        ${liste(geraete, "geraete",
          "Keine Geräte mit der Home-Assistant-App gefunden.")}
      </div>
      <div class="dialog-knoepfe">
        <button class="knopf leise" type="button" data-abbrechen>Abbrechen</button>
        <button class="knopf" type="button" data-speichern>Anlegen</button>
      </div>
    `;
    this._dialogEl
      .querySelector("[data-abbrechen]")
      .addEventListener("click", () => this._dialogSchliessen());
    this._dialogEl
      .querySelector("[data-speichern]")
      .addEventListener("click", () => this._speichern());
    this._huelleEl.hidden = false;
    this._dialogEl.querySelector("#uz-ziel").focus();
  }

  _dialogSchliessen() {
    this._huelleEl.hidden = true;
    this._dialogEl.innerHTML = "";
  }

  _fehlerZeigen(text) {
    const el = this._dialogEl.querySelector(".fehler");
    el.textContent = text;
    el.hidden = false;
  }

  async _speichern() {
    const gewaehlt = (name) =>
      [...this._dialogEl.querySelectorAll(`input[name="${name}"]:checked`)].map(
        (e) => e.value,
      );

    const teilnehmer = gewaehlt("teilnehmer");
    const ziel = this._dialogEl.querySelector("#uz-ziel").value.trim();
    const datum = this._dialogEl.querySelector("#uz-datum").value;
    const zeit = this._dialogEl.querySelector("#uz-zeit").value;

    if (!teilnehmer.length) {
      return this._fehlerZeigen("Bitte auswählen, wer in den Urlaub fährt.");
    }
    if (!ziel) return this._fehlerZeigen("Bitte ein Reiseziel eintragen.");
    if (!datum || !zeit) {
      return this._fehlerZeigen("Bitte Datum und Uhrzeit angeben.");
    }
    if (new Date(`${datum}T${zeit}`) <= new Date()) {
      return this._fehlerZeigen("Der Reisebeginn muss in der Zukunft liegen.");
    }

    const knopf = this._dialogEl.querySelector("[data-speichern]");
    knopf.disabled = true;
    knopf.textContent = "Wird angelegt …";

    const namen = teilnehmer.map(
      (id) => this._hass.states[id]?.attributes?.anzeigename ?? id,
    );
    const automatisierungsId = String(Date.now());
    try {
      await this._hass.callApi(
        "POST",
        `config/automation/config/${automatisierungsId}`,
        {
          alias: `Urlaub ${namen.join(", ")} – ${ziel}`,
          description: "Angelegt über die Urlaubszähler-Karte",
          use_blueprint: {
            path: this._config.blueprint_path,
            input: {
              teilnehmer,
              ziel,
              start: `${datum} ${zeit}:00`,
              mobilgeraete: gewaehlt("geraete"),
            },
          },
        },
      );
      await this._sofortAusfuehren(automatisierungsId);
      this._dialogSchliessen();
    } catch (fehler) {
      knopf.disabled = false;
      knopf.textContent = "Anlegen";
      this._fehlerZeigen(
        `Konnte nicht angelegt werden: ${fehler?.body?.message || fehler?.message || fehler}`,
      );
    }
  }

  /**
   * Die frisch gespeicherte Automatisierung einmal anstoßen.
   *
   * Home Assistant feuert 'automation_reloaded', bevor die Trigger der neuen
   * Automatisierung hängen - ohne diesen Anstoß erschiene der Sensor erst beim
   * nächsten Neuladen.
   */
  async _sofortAusfuehren(automatisierungsId) {
    for (let versuch = 0; versuch < 12; versuch++) {
      await new Promise((weiter) => setTimeout(weiter, 400));
      const treffer = Object.values(this._hass.states).find(
        (z) =>
          z.entity_id.startsWith("automation.") &&
          z.attributes?.id === automatisierungsId,
      );
      if (!treffer) continue;
      await this._hass.callService("automation", "trigger", {
        entity_id: treffer.entity_id,
        skip_condition: true,
      });
      return true;
    }
    return false;
  }

  _countdownAktualisieren() {
    if (!this._listenEl) return;
    const jetzt = Date.now();
    this._listenEl.querySelectorAll("[data-count]").forEach((el) => {
      const urlaub = this._urlaube[Number(el.dataset.count)];
      if (!urlaub) return;
      const r = restzeit(urlaub.zeitstempel, jetzt);
      el.innerHTML =
        `<b>${r.tage}</b> T &middot; <b>${r.stunden}</b> Std ` +
        `&middot; <b>${r.minuten}</b> Min`;
    });
  }

  _zeitpunkt(zeitstempel) {
    const sprache = this._hass?.locale?.language || "de";
    try {
      return new Date(zeitstempel * 1000).toLocaleString(sprache, {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: this._hass?.config?.time_zone || undefined,
      });
    } catch (fehler) {
      return new Date(zeitstempel * 1000).toLocaleString();
    }
  }
}

/* --------------------------------------------------------------------------
 * Grafischer Konfigurations-Editor
 * ------------------------------------------------------------------------ */

const EDITOR_SCHEMA = [
  { name: "title", selector: { text: {} } },
  { name: "show_map", selector: { boolean: {} } },
  {
    name: "map_height",
    selector: { number: { min: 120, max: 600, step: 10, mode: "slider" } },
  },
  { name: "max", selector: { number: { min: 0, max: 25, mode: "box" } } },
  { name: "show_add", selector: { boolean: {} } },
];

const EDITOR_TEXTE = {
  title: "Überschrift",
  show_map: "Weltkarte anzeigen",
  map_height: "Höhe der Karte (Pixel)",
  max: "Höchstzahl angezeigter Urlaube (0 = alle)",
  show_add: "Knopf zum Anlegen eines Urlaubs zeigen",
};

class UrlaubszaehlerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: "Urlaubszähler", show_map: true, map_height: 260, max: 0,
      show_add: true, ...config,
    };
    this._rendern();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _rendern() {
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = EDITOR_SCHEMA;
      this._form.computeLabel = (feld) => EDITOR_TEXTE[feld.name] ?? feld.name;
      this._form.addEventListener("value-changed", (ereignis) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: ereignis.detail.value },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.appendChild(this._form);
    }
    if (this._hass) this._form.hass = this._hass;
    this._form.data = this._config;
  }
}

customElements.define("urlaubszaehler-card", UrlaubszaehlerCard);
customElements.define("urlaubszaehler-card-editor", UrlaubszaehlerCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "urlaubszaehler-card",
  name: "Urlaubszähler",
  description:
    "Countdown-Liste aller geplanten Urlaube mit Weltkarte und Reisebögen.",
  preview: true,
  documentationURL: "https://github.com/frecem/urlaubszaehler",
});

console.info(
  `%c URLAUBSZAEHLER-CARD %c ${KARTEN_VERSION} `,
  "color: white; background: #03a9f4; font-weight: 700;",
  "color: #03a9f4; background: white; font-weight: 700;",
);
