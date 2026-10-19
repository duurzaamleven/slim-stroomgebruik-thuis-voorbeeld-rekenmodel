# SPDX-License-Identifier: EUPL-1.2
"""
tijdas.py: zomertijd-correcte tijd-as over een kalenderjaar.

Waarom dit een eigen module is en geen bijzaak: het legt de zomertijdvalkuil
bloot (twee omschakelmomenten per jaar: in het voorjaar verdwijnt een
klokuur, in het najaar komt het dubbel terug) op de goedkoopst mogelijke
manier, en het is meteen de as waarop de PV- en batterijlaag draaien.

Aanpak
------
We bouwen de as **niet** door lokale kloktijden één voor één op te tellen
(dat loopt vast op het niet-bestaande voorjaarsuur en het dubbelzinnige
najaarsuur), maar door:

1. de lokale jaargrenzen (1 januari 00:00 lokale tijd, start én eind) om te
   zetten naar UTC: dat kán altijd ondubbelzinnig, want 1 januari 00:00 valt
   in Nederland nooit in de zomertijd;
2. daartussen een **uniform gespatieerd UTC-rooster** te leggen met de
   gevraagde intervallengte;
3. dat rooster terug te labelen naar de lokale tijdzone.

Stap 3 toont het skippen/dubbel-tellen vanzelf: de UTC-instanten liggen
gegarandeerd equidistant, maar hun lokale kloklabels slaan in het voorjaar een
uur over en herhalen in het najaar een uur: precies het verschijnsel dat een
schil moet kunnen verwerken. Er is geen ambiguë-tijd-afhandeling nodig, omdat
we nooit lokale tijd genereren; we lezen hem alleen af.

Gebruikt ``zoneinfo`` (standaardbibliotheek); op Windows is het pakket
``tzdata`` nodig (zie requirements.txt).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

#: Toegestane intervallengtes in minuten. Kwartier = 35.040 intervallen over
#: een gewoon jaar (365 dagen); uur = 8.760.
TOEGESTANE_INTERVALLEN_MIN = (15, 60)


@dataclass(frozen=True)
class TijdAs:
    """Eén jaar aan tijdstempels, plus de metadata om hem te interpreteren."""
    index: pd.DatetimeIndex     # tz-bewust, in de opgegeven tijdzone
    kalenderjaar: int
    interval_min: int
    tijdzone__str: str

    def __len__(self) -> int:
        return len(self.index)


def bouw_tijd_as(kalenderjaar: int, interval_min: int, tijdzone__str: str = "Europe/Amsterdam") -> TijdAs:
    """Bouw een zomertijd-correcte tijd-as over ``kalenderjaar``.

    Parameters
    ----------
    kalenderjaar : het te simuleren jaar (bv. 2023).
    interval_min : intervallengte in minuten; 15 of 60 (zie
                   ``TOEGESTANE_INTERVALLEN_MIN``).
    tijdzone__str: IANA-tijdzonenaam, standaard Europe/Amsterdam.

    Returns
    -------
    TijdAs met een tz-bewuste ``DatetimeIndex`` van 1 januari 00:00 lokale
    tijd (inclusief) tot 1 januari 00:00 van het jaar erna (exclusief).
    """
    if interval_min not in TOEGESTANE_INTERVALLEN_MIN:
        raise ValueError(
            f"interval_min moet één van {TOEGESTANE_INTERVALLEN_MIN} zijn, kreeg {interval_min}")

    tz = ZoneInfo(tijdzone__str)
    start_lokaal = datetime(kalenderjaar, 1, 1, 0, 0, tzinfo=tz)
    eind_lokaal = datetime(kalenderjaar + 1, 1, 1, 0, 0, tzinfo=tz)

    # Stap 1: ondubbelzinnige UTC-jaargrenzen (1 jan 00:00 valt nooit in DST).
    start_utc = pd.Timestamp(start_lokaal).tz_convert("UTC")
    eind_utc = pd.Timestamp(eind_lokaal).tz_convert("UTC")

    # Stap 2: uniform UTC-rooster, exclusief het eindpunt.
    rooster_utc = pd.date_range(start=start_utc, end=eind_utc, freq=f"{interval_min}min",
                                 inclusive="left")

    # Stap 3: terug labelen naar lokale tijd: hier "gebeurt" de zomertijd.
    index = rooster_utc.tz_convert(tz)
    return TijdAs(index=index, kalenderjaar=kalenderjaar, interval_min=interval_min,
                  tijdzone__str=tijdzone__str)
