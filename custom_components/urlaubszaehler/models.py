"""Datenmodelle des Urlaubszählers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from . import distanz, zielzeit
from .const import ANKUNFTSZEIT_SCHWELLE, AUTO_DELETE_AFTER, TRANSPORTMITTEL_STANDARD


def format_namen(namen: list[str]) -> str:
    """Baue eine natürlichsprachige Aufzählung: 'Papa, Mama und Kind'."""
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
    transportmittel: str = TRANSPORTMITTEL_STANDARD

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

    def entfernung_km(self, heimat_lat: float, heimat_lon: float) -> float | None:
        """Luftlinienentfernung zum Ziel; None ohne bekannte Koordinaten."""
        if not self.hat_koordinaten:
            return None
        return distanz.entfernung_km(
            heimat_lat, heimat_lon, self.breitengrad, self.laengengrad
        )

    def reisedauer_stunden(
        self, heimat_lat: float, heimat_lon: float
    ) -> float | None:
        """Grobe Reisedauer-Schätzung in Stunden.

        None ohne Koordinaten oder bei Transportmittel "unbekannt" - dann
        fehlt schlicht die Grundlage für eine Schätzung.
        """
        entfernung = self.entfernung_km(heimat_lat, heimat_lon)
        if entfernung is None:
            return None
        return distanz.schaetze_dauer_stunden(self.transportmittel, entfernung)

    def reisedauer_text(self, heimat_lat: float, heimat_lon: float) -> str | None:
        """Menschenlesbare Reisedauer, z. B. 'ca. 8 Std.'."""
        stunden = self.reisedauer_stunden(heimat_lat, heimat_lon)
        if stunden is None:
            return None
        return distanz.formatiere_dauer(stunden)

    def ankunft(self, heimat_lat: float, heimat_lon: float) -> datetime | None:
        """Geschätzte Ankunftszeit in der Ortszeit am Ziel.

        None ohne Reisedauer-Schätzung (kein Transportmittel oder keine
        Koordinaten - siehe reisedauer_stunden()).
        """
        stunden = self.reisedauer_stunden(heimat_lat, heimat_lon)
        if stunden is None:
            return None
        ankunft_heimatzeit = self.start + timedelta(hours=stunden)
        return zielzeit.in_ortszeit(
            ankunft_heimatzeit, self.breitengrad, self.laengengrad
        )

    def ankunftszeit_text(
        self, heimat_lat: float, heimat_lon: float, jetzt: datetime | None = None
    ) -> str | None:
        """'Ankunft ca. 22:15 Uhr Ortszeit' - aber erst kurz vor der Abreise.

        Weiter im Voraus wäre eine exakte Uhrzeit bei einer ohnehin groben
        Reisedauer-Schätzung unpassend präzise (siehe ANKUNFTSZEIT_SCHWELLE) -
        bis dahin zählt nur die Dauer (reisedauer_text).
        """
        rest = self.restzeit(jetzt)
        if rest.sekunden > ANKUNFTSZEIT_SCHWELLE.total_seconds():
            return None
        zeitpunkt = self.ankunft(heimat_lat, heimat_lon)
        if zeitpunkt is None:
            return None
        return f"Ankunft ca. {zeitpunkt.strftime('%H:%M')} Uhr Ortszeit"

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
            "transportmittel": self.transportmittel,
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
            # get() statt [] : ältere, vor 1.0.5 gespeicherte Urlaube kennen
            # dieses Feld noch nicht und bekommen den Standardwert.
            transportmittel=daten.get("transportmittel", TRANSPORTMITTEL_STANDARD),
        )
