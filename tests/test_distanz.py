"""Tests für die grobe Entfernungs-/Reisedauer-Schätzung (distanz.py)."""

from __future__ import annotations

import pytest

from custom_components.urlaubszaehler.distanz import (
    entfernung_km,
    formatiere_dauer,
    schaetze_dauer_stunden,
)

BERLIN = (52.5200, 13.4050)
PARIS = (48.8566, 2.3522)


def test_entfernung_bekanntes_beispiel():
    """Berlin–Paris liegt bekanntermaßen bei rund 878 km Luftlinie."""
    ergebnis = entfernung_km(*BERLIN, *PARIS)
    assert ergebnis == pytest.approx(878, rel=0.03)


def test_entfernung_ist_symmetrisch():
    hin = entfernung_km(*BERLIN, *PARIS)
    zurueck = entfernung_km(*PARIS, *BERLIN)
    assert hin == pytest.approx(zurueck)


def test_entfernung_beim_selben_punkt_null():
    assert entfernung_km(*BERLIN, *BERLIN) == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize(
    "transportmittel,erwartet_std",
    [
        ("flugzeug", 900 / 800 + 2.0),  # Luftlinie direkt + 2 Std. Vorlauf
        ("auto", 900 * 1.3 / 90 + 1.0),  # Umweg + zwei 30-Min-Pausen
        ("bahn", 900 * 1.2 / 120),
        ("schiff", 900 * 1.1 / 35),
    ],
)
def test_schaetze_dauer_je_transportmittel(transportmittel, erwartet_std):
    ergebnis = schaetze_dauer_stunden(transportmittel, 900)
    assert ergebnis == pytest.approx(erwartet_std, rel=1e-6)


def test_schaetze_dauer_unbekanntes_transportmittel_gibt_none():
    assert schaetze_dauer_stunden("unbekannt", 900) is None
    assert schaetze_dauer_stunden("rakete", 900) is None


@pytest.mark.parametrize(
    "stunden,erwartet",
    [
        (0.3, "ca. 1 Std."),  # nie 'ca. 0 Std.'
        (1.125, "ca. 1 Std."),
        (8.4, "ca. 8 Std."),
        (14.0, "ca. 14 Std."),
        (26.0, "ca. 1 Tag 2 Std."),
        (48.0, "ca. 2 Tage"),
    ],
)
def test_formatiere_dauer(stunden, erwartet):
    assert formatiere_dauer(stunden) == erwartet
