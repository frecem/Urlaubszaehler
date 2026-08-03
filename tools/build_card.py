#!/usr/bin/env python3
"""Baut die Lovelace-Karte der Integration aus Quelle und Kartendaten.

Die Weltkarte stammt von Natural Earth (gemeinfrei, naturalearthdata.com).
Der Datensatz wird heruntergeladen, auf ein für eine Übersichtskarte sinnvolles
Maß vereinfacht und anschließend delta-/varint-kodiert in die Karte eingebettet
(~35 KB statt ~118 KB als JSON). Es sind keine externen Abhängigkeiten nötig.

Aufruf aus dem Wurzelverzeichnis des Repos:

    python3 tools/build_card.py
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import urllib.request

QUELLE = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_0_countries.geojson"
)
TOLERANZ = 0.18  # Grad; Stärke der Linienvereinfachung
MIN_FLAECHE = 0.5  # Quadratgrad; kleinere Inseln entfallen
NACHKOMMA = 2  # ~1 km Genauigkeit, für eine Weltkarte reichlich

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

WURZEL = pathlib.Path(__file__).resolve().parent.parent
QUELLDATEI = WURZEL / "tools" / "urlaubszaehler-card.src.js"
ZIELDATEI = (
    WURZEL / "custom_components" / "urlaubszaehler" / "frontend"
    / "urlaubszaehler-card.js"
)
ZWISCHENABLAGE = WURZEL / "tools" / ".ne_50m_countries.geojson"


def rdp(punkte: list[tuple[float, float]], toleranz: float):
    """Linienvereinfachung nach Ramer-Douglas-Peucker."""
    if len(punkte) < 3:
        return punkte
    behalten = [False] * len(punkte)
    behalten[0] = behalten[-1] = True
    stapel = [(0, len(punkte) - 1)]
    while stapel:
        start, ende = stapel.pop()
        ax, ay = punkte[start]
        bx, by = punkte[ende]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        groesster, index = 0.0, -1
        for i in range(start + 1, ende):
            px, py = punkte[i]
            abstand = (
                math.hypot(px - ax, py - ay)
                if norm == 0
                else abs(dy * px - dx * py + bx * ay - by * ax) / norm
            )
            if abstand > groesster:
                groesster, index = abstand, i
        if groesster > toleranz and index > 0:
            behalten[index] = True
            stapel.append((start, index))
            stapel.append((index, ende))
    return [p for p, k in zip(punkte, behalten) if k]


def flaeche(ring: list[tuple[float, float]]) -> float:
    """Betrag der Fläche eines geschlossenen Rings (Gauß-Formel)."""
    summe = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        summe += x1 * y2 - x2 * y1
    return abs(summe) / 2


def kodiere_wert(wert: int, ausgabe: list[str]) -> None:
    """Zickzack- und Varint-Kodierung eines Deltas."""
    zahl = (wert << 1) ^ (wert >> 31) if wert < 0 else (wert << 1)
    while True:
        rest = zahl & 31
        zahl >>= 5
        ausgabe.append(ALPHABET[rest | 32] if zahl else ALPHABET[rest])
        if not zahl:
            return


def kodiere(ringe) -> str:
    """Alle Ringe delta-kodiert aneinanderreihen."""
    teile = []
    for ring in ringe:
        ausgabe: list[str] = []
        letztes_x = letztes_y = 0
        for x, y in ring:
            ix, iy = round(x * 10**NACHKOMMA), round(y * 10**NACHKOMMA)
            kodiere_wert(ix - letztes_x, ausgabe)
            kodiere_wert(iy - letztes_y, ausgabe)
            letztes_x, letztes_y = ix, iy
        teile.append("".join(ausgabe))
    return "|".join(teile)


def dekodiere(text: str):
    """Gegenprobe zur JavaScript-Dekodierung in der Karte."""
    ringe = []
    for teil in text.split("|"):
        i = x = y = 0
        ring = []
        while i < len(teil):
            werte = []
            for _ in range(2):
                zahl, schub = 0, 0
                while True:
                    zeichen = ALPHABET.index(teil[i])
                    i += 1
                    zahl |= (zeichen & 31) << schub
                    schub += 5
                    if not zeichen & 32:
                        break
                werte.append((zahl >> 1) ^ -(zahl & 1))
            x += werte[0]
            y += werte[1]
            ring.append((x / 10**NACHKOMMA, y / 10**NACHKOMMA))
        ringe.append(ring)
    return ringe


def main() -> int:
    if not ZWISCHENABLAGE.exists():
        print(f"Lade {QUELLE} …")
        with urllib.request.urlopen(QUELLE) as antwort:
            ZWISCHENABLAGE.write_bytes(antwort.read())

    daten = json.loads(ZWISCHENABLAGE.read_text())
    ringe = []
    for merkmal in daten["features"]:
        geometrie = merkmal["geometry"]
        polygone = (
            [geometrie["coordinates"]]
            if geometrie["type"] == "Polygon"
            else geometrie["coordinates"]
        )
        for polygon in polygone:
            aussenring = [tuple(p[:2]) for p in polygon[0]]
            if flaeche(aussenring) < MIN_FLAECHE:
                continue
            gerundet: list[tuple[float, float]] = []
            for x, y in rdp(aussenring, TOLERANZ):
                punkt = (round(x, NACHKOMMA), round(y, NACHKOMMA))
                if not gerundet or punkt != gerundet[-1]:
                    gerundet.append(punkt)
            if len(gerundet) >= 4:
                ringe.append(gerundet)

    kodiert = kodiere(ringe)
    assert '"' not in kodiert and "\\" not in kodiert, "Alphabet nicht string-sicher"
    assert dekodiere(kodiert) == ringe, "Kodierung und Dekodierung passen nicht zusammen"

    quelle = QUELLDATEI.read_text()
    if "__WORLD__" not in quelle:
        print("FEHLER: Platzhalter __WORLD__ fehlt in der Quelldatei", file=sys.stderr)
        return 1

    ZIELDATEI.parent.mkdir(parents=True, exist_ok=True)
    ZIELDATEI.write_text(quelle.replace("__WORLD__", kodiert))

    punkte = sum(len(r) for r in ringe)
    print(
        f"{len(ringe)} Ringe, {punkte} Punkte -> {len(kodiert) / 1024:.1f} KB Kartendaten"
    )
    print(f"geschrieben: {ZIELDATEI.relative_to(WURZEL)} "
          f"({ZIELDATEI.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
