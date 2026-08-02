"""Datenmodelle des Urlaubszählers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import AUTO_DELETE_AFTER


def format_namen(namen: list[str]) -> str:
    """Baue eine natürlichsprachige Aufzählung: 'Papa, Fiene und Mama'."""
    namen = [n for n in namen if n]
    if not namen:
        return "unbekannt"
    if len(namen) == 1:
        return namen[0]
    return f"{', '.join(namen[:-1])} und {namen[-1]}"


def to_local(wert: datetime) -> datetime:
    """Interpretiere einen Zeitpunkt in der in Home Assistant eingestellten Zeitzone.

    Naive Zeitangaben (z. B. aus dem Datum/Zeit-Selector eines Blueprints)
    werden bewusst als lokale Zeit gelesen - bei einer HA-Konfiguration mit
    ``Europe/Berlin`` also als deutsche Zeit inklusive Sommer-/Winterzeit.
    """
    if wert.tzinfo is None:
        return wert.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_local(wert)


@dataclass
class Restzeit:
    """Verbleibende Zeit bis zum Reisebeginn (nie negativ)."""

    sekunden: int
    tage: int
    stunden: int
    minuten: int

    @classmethod
    def from_seconds(cls, sekunden: float) -> Restzeit:
        """Erzeuge die Restzeit aus Sekunden; negative Werte werden auf 0 geklemmt."""
        rest = max(0, int(sekunden))
        return cls(
            sekunden=rest,
            tage=rest // 86400,
            stunden=(rest % 86400) // 3600,
            minuten=(rest % 3600) // 60,
        )


@dataclass
class Vacation:
    """Ein geplanter Urlaub."""

    urlaub_id: str
    namen: list[str]
    ziel: str
    start: datetime
    arten: list[str] = field(default_factory=list)
    mitglieder: list[str] = field(default_factory=list)
    breitengrad: float | None = None
    laengengrad: float | None = None
    koordinaten_quelle: str | None = None
    gefunden_als: str | None = None

    def __post_init__(self) -> None:
        self.start = to_local(self.start)

    # ------------------------------------------------------------------
    # Abgeleitete Werte
    # ------------------------------------------------------------------
    @property
    def wer(self) -> str:
        """Formatierte Aufzählung der Reisenden."""
        return format_namen(self.namen)

    @property
    def start_ts(self) -> float:
        """Reisebeginn als Unix-Zeit (Dezimal, Sekunden seit Epoch)."""
        return self.start.timestamp()

    @property
    def delete_at(self) -> datetime:
        """Zeitpunkt, zu dem der Sensor restlos entfernt wird.

        Bewusst über UTC gerechnet: eine Addition auf der lokalen Zeit würde an
        der Zeitumstellung 23 oder 25 echte Stunden ergeben statt der
        geforderten 24.
        """
        return dt_util.as_local(
            self.start.astimezone(dt_util.UTC) + AUTO_DELETE_AFTER
        )

    @property
    def delete_ts(self) -> float:
        """Löschzeitpunkt als Unix-Zeit."""
        return self.start_ts + AUTO_DELETE_AFTER.total_seconds()

    def restzeit(self, jetzt: datetime | None = None) -> Restzeit:
        """Verbleibende Zeit bis zum Reisebeginn."""
        jetzt = jetzt or dt_util.utcnow()
        return Restzeit.from_seconds(self.start_ts - jetzt.timestamp())

    def ist_abgelaufen(self, jetzt: datetime | None = None) -> bool:
        """True, wenn der Urlaub länger als 24 Stunden zurückliegt."""
        jetzt = jetzt or dt_util.utcnow()
        return jetzt.timestamp() >= self.delete_ts

    def nachricht(self, jetzt: datetime | None = None) -> str:
        """Der vom Nutzer gewünschte Satz."""
        rest = self.restzeit(jetzt)
        return (
            f"Der Urlaub von {self.wer} ist in {rest.tage} Tagen, "
            f"{rest.stunden} Stunden und {rest.minuten} Minuten. "
            f"Die Reise geht nach {self.ziel}."
        )

    # ------------------------------------------------------------------
    # Serialisierung
    # ------------------------------------------------------------------
    @property
    def hat_koordinaten(self) -> bool:
        """True, wenn das Ziel auf der Karte dargestellt werden kann."""
        return self.breitengrad is not None and self.laengengrad is not None

    def as_dict(self) -> dict[str, Any]:
        """Für den persistenten Speicher."""
        return {
            "urlaub_id": self.urlaub_id,
            "namen": self.namen,
            "ziel": self.ziel,
            "start": self.start.isoformat(),
            "arten": self.arten,
            "mitglieder": self.mitglieder,
            "breitengrad": self.breitengrad,
            "laengengrad": self.laengengrad,
            "koordinaten_quelle": self.koordinaten_quelle,
            "gefunden_als": self.gefunden_als,
        }

    @classmethod
    def from_dict(cls, daten: dict[str, Any]) -> Vacation:
        """Aus dem persistenten Speicher lesen."""
        start = dt_util.parse_datetime(daten["start"])
        if start is None:  # pragma: no cover - defensiv
            start = dt_util.utcnow() + timedelta(days=1)
        return cls(
            urlaub_id=daten["urlaub_id"],
            namen=list(daten.get("namen", [])),
            ziel=daten.get("ziel", ""),
            start=start,
            arten=list(daten.get("arten", [])),
            mitglieder=list(daten.get("mitglieder", [])),
            breitengrad=daten.get("breitengrad"),
            laengengrad=daten.get("laengengrad"),
            koordinaten_quelle=daten.get("koordinaten_quelle"),
            gefunden_als=daten.get("gefunden_als"),
        )
