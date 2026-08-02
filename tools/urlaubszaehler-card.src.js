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

const KARTEN_VERSION = "1.0.0";

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
      ...config,
    };
    this._signatur = "";
    this._aufbauen();
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
      </ha-card>
    `;
    this._kopfEl = this.shadowRoot.querySelector(".kopf");
    this._kartenEl = this.shadowRoot.querySelector(".karte");
    this._listenEl = this.shadowRoot.querySelector(".liste");
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
];

const EDITOR_TEXTE = {
  title: "Überschrift",
  show_map: "Weltkarte anzeigen",
  map_height: "Höhe der Karte (Pixel)",
  max: "Höchstzahl angezeigter Urlaube (0 = alle)",
};

class UrlaubszaehlerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { title: "Urlaubszähler", show_map: true, map_height: 260, max: 0, ...config };
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
