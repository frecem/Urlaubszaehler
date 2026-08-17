"""Grobe Schätzung von Entfernung und Reisedauer zum Reiseziel.

Bewusst eine feste Faustformel statt einer echten Routenberechnung: es geht
nur um Pi-mal-Daumen-Werte für die Kartenanzeige, ohne externe Abhängigkeit
oder Netzwerkaufruf. Fähren o. Ä. werden nicht berücksichtigt - bei
Auto-/Bahnzielen über größere Wasserflächen (z. B. "Auto nach Mallorca")
liefert das bewusst in Kauf genommenen Unsinn statt eine Sonderbehandlung
einzubauen (siehe ROADMAP.md, "Zu klärende Details vor der Umsetzung").
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Final

ERDRADIUS_KM: Final = 6371.0


def entfernung_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Luftlinienentfernung zwischen zwei Koordinaten (Haversine-Formel)."""
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * ERDRADIUS_KM * asin(sqrt(a))


@dataclass(frozen=True)
class _Faustformel:
    """Parameter der Reisedauer-Schätzung für ein Transportmittel."""

    geschwindigkeit_kmh: float
    umwegfaktor: float  # gegenüber der Luftlinie (Straßen-/Streckenverlauf)
    pause_alle_std: float | None = None
    pause_dauer_std: float = 0.0
    vorlauf_std: float = 0.0  # z. B. Sicherheitskontrolle beim Flug


_FAUSTFORMELN: Final[dict[str, _Faustformel]] = {
    "flugzeug": _Faustformel(
        geschwindigkeit_kmh=800, umwegfaktor=1.0, vorlauf_std=2.0
    ),
    "auto": _Faustformel(
        geschwindigkeit_kmh=90,
        umwegfaktor=1.3,
        pause_alle_std=4.5,
        pause_dauer_std=0.5,
    ),
    "bahn": _Faustformel(geschwindigkeit_kmh=120, umwegfaktor=1.2),
    "schiff": _Faustformel(geschwindigkeit_kmh=35, umwegfaktor=1.1),
}


def schaetze_dauer_stunden(transportmittel: str, entfernung: float) -> float | None:
    """Grobe Reisedauer in Stunden; None bei unbekanntem Transportmittel."""
    formel = _FAUSTFORMELN.get(transportmittel)
    if formel is None:
        return None
    strecke = entfernung * formel.umwegfaktor
    fahrzeit_std = strecke / formel.geschwindigkeit_kmh
    pausen_std = 0.0
    if formel.pause_alle_std:
        pausen_std = (fahrzeit_std // formel.pause_alle_std) * formel.pause_dauer_std
    return fahrzeit_std + pausen_std + formel.vorlauf_std


def formatiere_dauer(stunden: float) -> str:
    """Menschenlesbarer Text, z. B. 'ca. 8 Std.' oder 'ca. 1 Tag 4 Std.'.

    Mindestens 1 Stunde, damit auch sehr kurze Strecken nicht als
    "ca. 0 Std." erscheinen - es ist ohnehin nur eine grobe Schätzung.
    """
    gerundet = max(1, round(stunden))
    tage, rest_std = divmod(gerundet, 24)
    tage_text = f"{tage} Tag{'e' if tage != 1 else ''}"
    if tage and rest_std:
        return f"ca. {tage_text} {rest_std} Std."
    if tage:
        return f"ca. {tage_text}"
    return f"ca. {rest_std} Std."
