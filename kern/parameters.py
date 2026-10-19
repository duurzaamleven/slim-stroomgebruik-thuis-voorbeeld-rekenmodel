# SPDX-License-Identifier: EUPL-1.2
"""
parameters.py: het invoerdatamodel van de rekenkern.

``SimulatieParameters`` is de platte invoer die de schil bouwt uit zijn eigen
bron (een CLI-argument, een webformulier, een testfixture: de kern kent geen
van die bronnen). Dit spiegelt bewust het invoerdatamodel van het echte
simulatiemodel: dezelfde soorten velden (scalair, categorisch, optioneel met
een default), dezelfde eenheidsconventie in de namen (``physiquant__unit``),
maar met veel minder velden: precies genoeg om de drie modellagen (tijd-as,
PV, thuisbatterij) te voeden.

De kern doet hier geen acquisitie en geen validatie tegen de buitenwereld: dat
is de taak van ``kern.behoeften`` (vóór de run) en van de schil (tijdens de
invoer). Deze module bevat alleen de vorm van de invoer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Landelijk gemiddelde locatie (bij benadering het midden van Nederland): de
# terugval als een schil geen adres/locatie aanlevert. Zie kern/behoeften.py.
STANDAARD_LAT__DEGN = 52.1326
STANDAARD_LON__DEGE = 5.2913

# Terugvalwaarden voor dakoriëntatie, zie ontwerp §5.7.
STANDAARD_AZIMUT__DEG = 180.0  # zuid, in de instraling-conventie (0 = noord, met de klok mee)
STANDAARD_HELLING__DEG = 35.0

StuurregelBatterij = Literal["eigen_verbruik", "prijssignaal"]


@dataclass(frozen=True)
class PVVeld:
    """Eén paneelveld met een gemeenschappelijke oriëntatie.

    Meerdere velden geven bv. een oost-west-opstelling. ``azimut__deg`` volgt
    de instraling-conventie: 0 = noord, met de klok mee, zuid = 180.
    """
    aantal_panelen__0: int
    azimut__deg: float = STANDAARD_AZIMUT__DEG
    hellingshoek__deg: float = STANDAARD_HELLING__DEG


@dataclass(frozen=True)
class BatterijParameters:
    """Parameters van de thuisbatterijlaag. Alleen relevant als ``batterij_toevoegen``."""
    capaciteit__kWh: float = 10.0
    laadvermogen__W: float = 3600.0
    ontlaadvermogen__W: float = 3600.0
    soc_min__0: float = 0.10
    soc_max__0: float = 0.95
    soc_initieel__0: float = 0.50
    retourrendement__W0: float = 0.90
    stuurregel__cat: StuurregelBatterij = "eigen_verbruik"


@dataclass(frozen=True)
class SimulatieParameters:
    """
    Alle invoer die de rekenkern nodig heeft, als platte waarden.

    Categorieën, ter illustratie van de drie soorten velden die het ontwerp
    (§4) van een invoerdatamodel eist:
      * scalair          : ``kalenderjaar``, ``interval_min``, ``locatie_lat__degN``
      * categorisch       : ``tijdzone``, ``batterij.stuurregel__cat``
      * optioneel-met-default: vrijwel alle overige velden
    """
    kalenderjaar: int
    interval_min: int = 60
    tijdzone__str: str = "Europe/Amsterdam"

    # Locatie: doellocatie van de zonpositie in de PV-laag én van de
    # geospatiale weerinterpolatie (zie kern/geo.py en kern/model.py): het
    # landelijke weerpakket wordt hiernaartoe geïnterpoleerd. Terugval:
    # landelijk gemiddelde (zie behoeften.py, grootheid "locatie_lat_lon").
    locatie_lat__degN: float = STANDAARD_LAT__DEGN
    locatie_lon__degE: float = STANDAARD_LON__DEGE

    # PV-laag.
    pv_toevoegen__bool: bool = True
    pv_velden: tuple[PVVeld, ...] = (PVVeld(aantal_panelen__0=12),)
    pv_vermogen_per_paneel__Wp: float = 440.0
    pv_omvormer_capaciteit__W: float = 5000.0
    pv_eta_omvormer__W0: float = 0.97
    pv_systeemverlies__0: float = 0.14

    # Thuisbatterijlaag.
    batterij_toevoegen__bool: bool = True
    batterij: BatterijParameters = field(default_factory=BatterijParameters)

    # Basislast (huishoudelijk verbruik exclusief PV/batterij): verbetert met een
    # gemeten tijdreeks (P1-poort e.d.); terugval: synthetisch profiel (zie behoeften.py).
    basislast_jaarverbruik__kWh: float = 3000.0

    # Kalibratie op een gemeten PV-opbrengst: puur verbeterend, zie behoeften.py.
    pv_kalibratie_toepassen__bool: bool = False
