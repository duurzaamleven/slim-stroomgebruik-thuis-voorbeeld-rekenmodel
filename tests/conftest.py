# SPDX-License-Identifier: EUPL-1.2
"""Gedeelde testfixtures voor de kern-tests.

Genereert een klein, deterministisch synthetisch **landelijk** (meerstations)
weerpakket in het geheugen, zonder afhankelijkheid van de gecommitte CSV's in
``pakketten/``, zodat deze tests ook slagen als dat databestand ooit
verandert. ``weerdata_2023``/``weerdata_2023_kwartier`` hebben, net als het
echte weerpakket, een 2-level kolom-``MultiIndex`` (grootheid, station_id):
``kern.model.simuleer`` interpoleert ze zelf naar ``standaard_invoer``'s
locatie (zie ``kern.geo``), samen met de bijbehorende ``weerstations``-fixture.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kern.parameters import BatterijParameters, PVVeld, SimulatieParameters
from kern.pv import zonpositie
from kern.tijdas import bouw_tijd_as

LAT__DEGN = 52.1326
LON__DEGE = 5.2913

# Zes synthetische meetpunten over een NL-achtige rechthoek, bewust dezelfde
# als in tests/test_geo.py en pakketten/weer_synthetisch_testfixture_stations_2023.csv:
# genoeg spreiding om de geo-interpolatie zinvol te toetsen, en met opzet geen
# van allen exact op STANDAARD_LAT__DEGN/STANDAARD_LON__DEGE (anders zou de
# doellocatie toevallig samenvallen met een station en levert dat geen
# betekenisvolle test van de interpolatie zelf op).
_STATIONS = pd.DataFrame(
    {
        "lat__degN": [53.00, 53.20, 51.20, 50.90, 52.10, 52.30],
        "lon__degE": [4.00, 6.90, 3.60, 5.90, 5.30, 4.80],
    },
    index=pd.Index(["st_nw", "st_no", "st_zw", "st_zo", "st_mid", "st_w"], name="station_id"),
)


def maak_weerdata_station(kalenderjaar: int, interval_min: int, lat__degN: float,
                           lon__degE: float) -> pd.DataFrame:
    """Bouw een deterministisch, plausibel weerpakket voor één locatie."""
    tijd_as = bouw_tijd_as(kalenderjaar, interval_min)
    index = tijd_as.index
    doy = index.dayofyear.to_numpy().astype(float)
    uur = index.hour.to_numpy().astype(float) + index.minute.to_numpy().astype(float) / 60.0

    zon = zonpositie(index, lat__degN, lon__degE)
    elevatie__deg = np.clip(zon.elevatie__deg, 0.0, None)

    temperatuur__degC = (9.5 - 8.0 * np.cos(2 * np.pi * (doy - 30) / 365.25)
                          + 3.0 * np.sin(2 * np.pi * (uur - 9) / 24.0))
    helder_hemel__W_m_2 = np.clip(1367.0 * zon.e0__0 * np.sin(np.radians(elevatie__deg)) * 0.72, 0.0, None)
    instraling__W_m_2 = np.where(elevatie__deg > 0, helder_hemel__W_m_2 * 0.75, 0.0)

    return pd.DataFrame({
        "temperatuur__degC": temperatuur__degC,
        "instraling__W_m_2": instraling__W_m_2,
        "windsnelheid__m_s": np.full(len(index), 4.0),
    }, index=index)


def maak_weerdata_meerstations(kalenderjaar: int, interval_min: int,
                                stations: pd.DataFrame = _STATIONS) -> pd.DataFrame:
    """Bouw een landelijk weerpakket: kolommen (grootheid, station_id), net als
    ``kern.model.simuleer`` verwacht (zie ``kern.model._interpoleer_weer_naar_locatie``)."""
    per_station = {
        station_id: maak_weerdata_station(kalenderjaar, interval_min, rij["lat__degN"], rij["lon__degE"])
        for station_id, rij in stations.iterrows()
    }
    gecombineerd = pd.concat(per_station, axis=1)  # niveau 0 wordt hier station_id
    return gecombineerd.swaplevel(axis=1).sort_index(axis=1, level=0)


@pytest.fixture
def weerstations() -> pd.DataFrame:
    return _STATIONS.copy()


@pytest.fixture
def weerdata_2023(weerstations) -> pd.DataFrame:
    return maak_weerdata_meerstations(2023, 60, weerstations)


@pytest.fixture
def weerdata_2023_kwartier(weerstations) -> pd.DataFrame:
    return maak_weerdata_meerstations(2023, 15, weerstations)


@pytest.fixture
def standaard_invoer() -> SimulatieParameters:
    return SimulatieParameters(
        kalenderjaar=2023,
        interval_min=60,
        locatie_lat__degN=LAT__DEGN,
        locatie_lon__degE=LON__DEGE,
        pv_toevoegen__bool=True,
        pv_velden=(PVVeld(aantal_panelen__0=12),),
        batterij_toevoegen__bool=True,
        batterij=BatterijParameters(),
        basislast_jaarverbruik__kWh=3000.0,
    )
