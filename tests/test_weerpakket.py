# SPDX-License-Identifier: EUPL-1.2
"""Het echte KNMI-weerpakket (``weer/knmi-nl-JJJJ``) als invoer van de kern.

Twee soorten tests:

* offline: een klein pakket in het KNMI-formaat, in het geheugen gemaakt,
  voor de omzetting in ``kern.weerpakket`` en het rekenen om gaten heen;
* met het echte pakket: een volledige jaarrun op een lokale kopie van
  ``slim-stroomgebruik-thuis-datapakketten``. Die repo staat niet in deze
  (openbare) repo; ontbreekt hij, dan worden deze tests overgeslagen. Zet
  ``DATAPAKKETTEN_MAP`` of zet de repo naast deze repo.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from kern.behoeften import behoeften, weerpakket_naam
from kern.model import simuleer
from kern.voortgang import Voortgang
from kern.weerpakket import KNMI_NAAR_KERN, knmi_weerpakket_naar_kern
from schil.cli import lees_knmi_weerpakket, zoek_datapakketten_map, zoek_pakket

from conftest import _STATIONS, maak_weerdata_station


def _knmi_formaat(kalenderjaar: int, stations: pd.DataFrame = _STATIONS) -> pd.DataFrame:
    """Een weerpakket in precies het formaat van ``weer/knmi-nl-JJJJ``: lang,
    met ``timestamp`` en ``lat__degN``/``lon__degE`` op elke rij."""
    delen = []
    for _, rij in stations.iterrows():
        weer = maak_weerdata_station(kalenderjaar, 60, rij["lat__degN"], rij["lon__degE"])
        delen.append(pd.DataFrame({
            "timestamp": weer.index,
            "lat__degN": rij["lat__degN"],
            "lon__degE": rij["lon__degE"],
            "buitentemperatuur__degC": weer["temperatuur__degC"].to_numpy(),
            "windsnelheid__m_s_1": weer["windsnelheid__m_s"].to_numpy(),
            "globale_straling__W_m_2": weer["instraling__W_m_2"].to_numpy(),
            "luchtdruk__Pa": 101325.0,
            "rel_vochtigheid__0": 0.8,
        }))
    return pd.concat(delen, ignore_index=True).sort_values(["timestamp", "lat__degN"], kind="stable")


# ── Offline ───────────────────────────────────────────────────────────────────

def test_behoeften_kiest_knmi_pakket_bij_kalenderjaar_2024(standaard_invoer):
    plan = behoeften(replace(standaard_invoer, kalenderjaar=2024))
    assert [p.naam__str for p in plan.pakketbehoeften] == ["weer/knmi-nl-2024"]


def test_omzetting_geeft_kernnamen_en_stationstabel():
    weerdata, weerstations = knmi_weerpakket_naar_kern(_knmi_formaat(2023))
    assert set(weerdata.columns.get_level_values(0)) == set(KNMI_NAAR_KERN.values())
    assert len(weerstations) == len(_STATIONS)
    assert set(weerdata.columns.get_level_values(1)) == set(weerstations.index)
    assert list(weerstations.columns) == ["lat__degN", "lon__degE"]
    assert weerdata.index.is_monotonic_increasing
    assert not weerdata.isna().any().any()


def test_omzetting_verandert_geen_waarden():
    """Alleen namen en vorm veranderen; de eenheden zijn gelijk, dus de getallen ook."""
    lang = _knmi_formaat(2023)
    weerdata, weerstations = knmi_weerpakket_naar_kern(lang)
    station_id = weerstations.index[0]
    lat, lon = weerstations.loc[station_id]
    bron = lang[(lang.lat__degN == lat) & (lang.lon__degE == lon)].set_index("timestamp")
    np.testing.assert_array_equal(
        weerdata[("temperatuur__degC", station_id)].to_numpy(), bron["buitentemperatuur__degC"].to_numpy())
    np.testing.assert_array_equal(
        weerdata[("instraling__W_m_2", station_id)].to_numpy(), bron["globale_straling__W_m_2"].to_numpy())


def test_omzetting_weigert_iets_wat_geen_knmi_pakket_is():
    with pytest.raises(ValueError, match="geen KNMI-weerpakket"):
        knmi_weerpakket_naar_kern(pd.DataFrame({"tijdstip": [], "temperatuur__degC": []}))


def test_omzetting_weigert_dubbele_rij():
    lang = _knmi_formaat(2023)
    with pytest.raises(ValueError):
        knmi_weerpakket_naar_kern(pd.concat([lang, lang.iloc[:1]]))


def test_simuleer_met_knmi_formaat_gelijk_aan_kernformaat(standaard_invoer, weerdata_2023, weerstations):
    """Via het KNMI-formaat rekenen geeft dezelfde uitkomst als met de
    bestaande in-memory fixture: de omzetting voegt niets toe en laat niets weg."""
    weerdata, stations = knmi_weerpakket_naar_kern(_knmi_formaat(2023))
    via_knmi = simuleer(standaard_invoer, weerdata=weerdata, weerstations=stations)
    direct = simuleer(standaard_invoer, weerdata=weerdata_2023, weerstations=weerstations)
    pd.testing.assert_frame_equal(via_knmi.intervallen, direct.intervallen, check_exact=False, rtol=1e-9)


def test_gat_bij_een_meetpunt_wordt_omheen_geinterpoleerd(standaard_invoer):
    """Een paar dagen zonder één meetpunt (zoals in knmi-nl-2024 en -2025) geeft
    geen NaN en geen doorgetrokken waarde, maar een interpolatie uit de rest."""
    lang = _knmi_formaat(2023)
    gat = (lang.lat__degN == _STATIONS.iloc[0]["lat__degN"]) & (
        lang.timestamp.between(pd.Timestamp("2023-06-10", tz="Europe/Amsterdam"),
                               pd.Timestamp("2023-06-14", tz="Europe/Amsterdam")))
    meldingen: list[Voortgang] = []
    weerdata, stations = knmi_weerpakket_naar_kern(lang[~gat])
    uitvoer = simuleer(standaard_invoer, weerdata=weerdata, weerstations=stations, meld=meldingen.append)
    assert uitvoer.status__cat == "voltooid"
    assert not uitvoer.intervallen.isna().any().any()
    assert any("ontbreekt een of meer meetpunten" in m.boodschap for m in meldingen)
    juni = uitvoer.intervallen.loc["2023-06-11":"2023-06-13", "pv_ac__W"]
    assert juni.max() > 0


def test_weer_van_het_verkeerde_jaar_geeft_waarschuwing(standaard_invoer, weerdata_2023, weerstations):
    meldingen: list[Voortgang] = []
    simuleer(replace(standaard_invoer, kalenderjaar=2024), weerdata=weerdata_2023,
             weerstations=weerstations, meld=meldingen.append)
    assert any(m.ernst == "waarschuwing" and "dekt" in m.boodschap for m in meldingen)


# ── Met het echte pakket uit slim-stroomgebruik-thuis-datapakketten ──────────

def _echt_pakket(kalenderjaar: int):
    map_ = zoek_datapakketten_map()
    if map_ is None:
        pytest.skip("geen lokale kopie van slim-stroomgebruik-thuis-datapakketten "
                    "(zet DATAPAKKETTEN_MAP of zet de repo naast deze repo)")
    import json
    manifest = json.loads((map_ / "manifest.json").read_text(encoding="utf-8"))
    pakket = zoek_pakket(manifest, weerpakket_naam(kalenderjaar), 1)
    if pakket is None:
        pytest.skip(f"{weerpakket_naam(kalenderjaar)} staat niet in {map_}")
    pytest.importorskip("pyarrow")
    return map_, pakket


@pytest.mark.parametrize("interval_min", [60, 15])
def test_volledige_jaarrun_op_knmi_2024(standaard_invoer, interval_min):
    map_, pakket = _echt_pakket(2024)
    weerdata, weerstations = lees_knmi_weerpakket(map_, pakket, interval_min)
    assert len(weerstations) == 22

    invoer = replace(standaard_invoer, kalenderjaar=2024, interval_min=interval_min)
    meldingen: list[Voortgang] = []
    uitvoer = simuleer(invoer, weerdata=weerdata, weerstations=weerstations, meld=meldingen.append)

    assert uitvoer.status__cat == "voltooid"
    assert uitvoer.aantal_intervallen == 366 * 24 * 60 // interval_min  # schrikkeljaar
    assert not uitvoer.intervallen.isna().any().any()
    # Het pakket dekt het hele jaar (met marge): geen doorgetrokken waarden.
    assert not any("dekt" in m.boodschap for m in meldingen)

    pv__kWh = uitvoer.intervallen["pv_ac__W"].sum() * interval_min / 60000.0
    # 12 x 440 Wp op het zuiden in Midden-Nederland: ruwweg 800-1000 kWh per kWp.
    assert 3500 < pv__kWh < 6000
    basislast__kWh = uitvoer.intervallen["basislast__W"].sum() * interval_min / 60000.0
    assert basislast__kWh == pytest.approx(3000.0, rel=1e-6)
