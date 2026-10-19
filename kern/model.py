# SPDX-License-Identifier: EUPL-1.2
"""
model.py: de formele modelinterface: ``simuleer(invoer) -> uitvoer``.

Dit is het enige aanroeppunt dat een schil hoeft te kennen (ontwerpdocument
§4). Alles eromheen (tijd-as, PV, batterij, behoefteplan) is domeinlaag die
``simuleer`` orkestreert.

Ontwerpregels die hier zichtbaar worden
----------------------------------------
* **Acquisitievrij**: ``simuleer`` accepteert weer-/prijsdata als parameter
  (``weerdata``, ``prijsdata__EUR_kWh``); hij haalt zelf niets op.
* **Geospatiaal**: ``weerdata`` is een **landelijk** pakket (alle stations
  tegelijk, zie ``kern.behoeften.WEERPAKKET_NAAM``); de kern interpoleert het
  zelf naar ``invoer.locatie_lat__degN``/``locatie_lon__degE`` (zie
  ``kern.geo`` en ``_interpoleer_weer_naar_locatie`` hieronder), zodat de
  locatie nooit naar de uitgever van het weerpakket hoeft.
* **Behoefteplan eerst**: vóór er wordt gerekend, wordt gecontroleerd of alle
  *verplichte* behoeften vervuld zijn (hier: het weerpakket). Ontbreekt dat,
  dan is de uitkomst status ``"onvolledig"``, geen exception (§5.6).
* **Annuleringspunt**: de enige plek waar de rekentijd evenredig oploopt met
  een Python-lus is de batterijlaag (toestand die door de tijd draagt, zie
  ``kern.batterij``); daar zit het annuleringspunt. Tijd-as en PV zijn
  vectorized en per interval onafhankelijk, dus daar is niets zinnigs af te
  breken.
* **Determinisme**: geen enkele stap hier gebruikt een niet-geseede randomgenerator
  of de systeemklok; gelijke invoer geeft dus bit-identieke uitvoer.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from .batterij import simuleer_batterij
from .behoeften import WEERPAKKET_NAAM, behoeften
from .cache import Cache
from .geo import geo_gewichten, interpoleer
from .parameters import SimulatieParameters
from .pv import pv_ac_vermogen__W
from .tijdas import bouw_tijd_as
from .uitvoer import CONTRACT_VERSIE, SimulatieUitvoer
from .voortgang import Melder, Voortgang, negeer_voortgang

#: Verwachte kolommen in het geïnjecteerde weerpakket (zie pakketten/manifest.json).
WEERKOLOM_TEMPERATUUR = "temperatuur__degC"
WEERKOLOM_STRALING = "instraling__W_m_2"

#: Kolomnamen van ``weerstations`` (zie ``_interpoleer_weer_naar_locatie``).
WEERSTATION_LAT = "lat__degN"
WEERSTATION_LON = "lon__degE"

#: Elke hoeveel batterij-intervallen het annuleringspunt wordt gepolld. Een
#: kleinere waarde maakt annuleren responsiever maar kost iets meer overhead;
#: 500 intervallen bij kwartier is ~5 dagen simulatietijd tussen twee polls.
ANNULERING_POLL_INTERVAL = 500

#: Boven dit aandeel daglicht-intervallen met omvormerclipping geven we een
#: waarschuwing: de omvormer is dan structureel te klein voor het paneelveld.
CLIPPING_WAARSCHUWING_DREMPEL__0 = 0.01


def _reindex_naar_tijdas(reeks: pd.Series | pd.DataFrame, doel_index: pd.DatetimeIndex):
    """Breng een tijdreeks van willekeurige (maar tz-bewuste) resolutie naar
    de doel-tijd-as, via tijdgebaseerde lineaire interpolatie.

    Gebruikt voor het geïnjecteerde weerpakket: dat kan op uurbasis staan
    terwijl de simulatie op kwartierbasis draait, of omgekeerd.
    """
    bron = reeks.tz_convert("UTC") if reeks.index.tz is not None else reeks.tz_localize("UTC")
    doel_utc = doel_index.tz_convert("UTC")
    samengevoegd_index = bron.index.union(doel_utc).sort_values()
    heraligned = bron.reindex(samengevoegd_index).interpolate(method="time").ffill().bfill()
    resultaat = heraligned.reindex(doel_utc)
    resultaat.index = doel_index
    return resultaat


def _interpoleer_weer_naar_locatie(
    weerdata: pd.DataFrame,
    weerstations: pd.DataFrame,
    doel_lat__degN: float,
    doel_lon__degE: float,
) -> pd.DataFrame:
    """Interpoleer een landelijk (meerstations) weerpakket naar één locatie.

    ``weerdata`` is een DataFrame met een 2-level kolom-``MultiIndex``:
    niveau 0 de grootheid (bv. ``"temperatuur__degC"``), niveau 1 het
    ``station_id`` (zoals bv. ``pandas.pivot_table`` dat oplevert als je een
    lang-formaat CSV pivotteert op ``station_id``). ``weerstations`` is een
    DataFrame, geïndexeerd op datzelfde ``station_id``, met de kolommen
    ``lat__degN``/``lon__degE``.

    Dit is de plek waar ``kern.geo`` in de kern wordt aangesloten: de
    gewichten worden hier precies één keer bepaald (``geo_gewichten``) en
    daarna op elke grootheid toegepast (``interpoleer``); zie de
    moduledocstring van ``kern.geo`` voor waarom dat exact, en niet slechts
    een benadering, is.
    """
    station_ids = list(weerstations.index)
    ontbrekend = set(station_ids) - set(weerdata.columns.get_level_values(1))
    if ontbrekend:
        raise ValueError(
            f"weerstations noemt stations die niet in weerdata voorkomen: {sorted(ontbrekend)}")

    stations__deg = weerstations.loc[station_ids, [WEERSTATION_LAT, WEERSTATION_LON]].to_numpy(dtype=float)
    gewichten = geo_gewichten(stations__deg, doel_lat__degN, doel_lon__degE)

    kolommen: dict[str, np.ndarray] = {}
    for grootheid in weerdata.columns.get_level_values(0).unique():
        waarden__t_n = weerdata[grootheid][station_ids].to_numpy(dtype=float)
        kolommen[grootheid] = interpoleer(waarden__t_n, gewichten)
    return pd.DataFrame(kolommen, index=weerdata.index)


def _synthetisch_basislastprofiel__W(index: pd.DatetimeIndex, interval_min: int,
                                      jaarverbruik__kWh: float) -> pd.Series:
    """Deterministisch synthetisch basislastprofiel (terugval, zie kern.behoeften).

    Puur een formule van tijd-kenmerken (uur van de dag, weekdag/weekend,
    dag van het jaar), geen randomgenerator, dus vanzelf deterministisch.
    Vorm: een ochtend- en een avondpiek, iets hoger verbruik in het weekend
    en in de winter (verlichting), genormaliseerd op het opgegeven jaarverbruik.
    """
    uur_frac = index.hour.to_numpy(dtype=float) + index.minute.to_numpy(dtype=float) / 60.0
    ochtend_piek = np.exp(-0.5 * ((uur_frac - 8.0) / 1.5) ** 2)
    avond_piek = np.exp(-0.5 * ((uur_frac - 19.5) / 2.0) ** 2)
    basis = 0.30 + 0.45 * ochtend_piek + 0.65 * avond_piek

    weekend_factor = np.where(index.dayofweek.to_numpy() >= 5, 1.15, 1.0)
    doy = index.dayofyear.to_numpy().astype(float)
    seizoen_factor = 1.0 + 0.15 * np.cos(2 * np.pi * (doy - 15) / 365.25)

    vorm = basis * weekend_factor * seizoen_factor
    vorm_genormaliseerd = vorm / vorm.sum()

    energie_per_interval__kWh = jaarverbruik__kWh * vorm_genormaliseerd
    vermogen__W = energie_per_interval__kWh * 1000.0 / (interval_min / 60.0)
    return pd.Series(vermogen__W, index=index, name="basislast__W")


def simuleer(
    invoer: SimulatieParameters,
    *,
    weerdata: pd.DataFrame | None = None,
    weerstations: pd.DataFrame | None = None,
    prijsdata__EUR_kWh: pd.Series | None = None,
    gemeten_basislast__W: pd.Series | None = None,
    gemeten_pv_opbrengst__kWh: pd.Series | None = None,
    cache: Cache | None = None,
    meld: Melder = negeer_voortgang,
    annuleer: Callable[[], bool] | None = None,
) -> SimulatieUitvoer:
    """Voer één jaarsimulatie uit: tijd-as → weer-interpolatie → PV → batterij → uitvoer.

    Parameters
    ----------
    invoer                     : SimulatieParameters (het invoerdatamodel).
    weerdata                   : geïnjecteerd **landelijk** weerpakket: een
                                  DataFrame met een 2-level kolom-``MultiIndex``
                                  (niveau 0 de grootheid, o.a.
                                  ``temperatuur__degC``/``instraling__W_m_2``;
                                  niveau 1 het ``station_id``) op een
                                  tz-bewuste DatetimeIndex. **Verplicht**
                                  (§5.7): zonder weer is er geen zinnige
                                  terugval en rekent de kern niet (zie
                                  ``kern.behoeften``).
    weerstations               : per ``station_id`` (dezelfde ids als in
                                  ``weerdata``) de kolommen ``lat__degN``/
                                  ``lon__degE``. Verplicht zodra ``weerdata``
                                  is gegeven: zonder stationscoördinaten valt
                                  er niets te interpoleren (zie ``kern.geo``).
    prijsdata__EUR_kWh         : geïnjecteerde prijsreeks; alleen nodig als
                                  de batterij op prijssignaal stuurt.
    gemeten_basislast__W       : optionele gemeten basislast (P1 e.d.);
                                  ontbreekt die, dan valt de kern terug op een
                                  synthetisch profiel (§5.7).
    gemeten_pv_opbrengst__kWh  : optionele meting voor PV-kalibratie; nu
                                  alleen meegedragen (geen kalibratielogica
                                  in deze toy: de terugval is "geen kalibratie").
    cache                      : optionele ``Cache``-implementatie (structureel
                                  protocol, zie ``kern.cache``); de kern gebruikt
                                  hem alleen om een dure afgeleide berekening
                                  niet dubbel te doen.
    meld                       : ``Melder`` voor ``Voortgang``-events.
    annuleer                   : callable zonder argumenten die ``True``
                                  teruggeeft zodra de aanroeper wil stoppen.
                                  Wordt periodiek gepolld in de batterijlaag
                                  (zie ``ANNULERING_POLL_INTERVAL``).

    Returns
    -------
    SimulatieUitvoer, nooit een exception voor een verwachte uitkomst
    (ontbrekende verplichte behoefte, annulering): die situaties komen terug
    als een ``status__cat`` die de schil kan interpreteren (§5.6). Een
    aanroep mét ``weerdata`` maar zonder ``weerstations`` is geen verwachte
    uitkomst maar een programmeerfout van de aanroeper (het landelijke
    pakket is zonder stationscoördinaten zinloos): dat geeft dus wél een
    ``ValueError``, net als een overduidelijk verkeerde vorm ergens anders in
    de kern.
    """
    plan = behoeften(invoer)
    if weerdata is None:
        meld(Voortgang("behoefteplan", f"verplichte behoefte ontbreekt: {WEERPAKKET_NAAM}",
                        ernst="waarschuwing"))
        return SimulatieUitvoer(
            contract_versie=CONTRACT_VERSIE,
            status__cat="onvolledig",
            intervallen=pd.DataFrame(),
            samenvatting=pd.DataFrame(),
            kalenderjaar=invoer.kalenderjaar,
            interval_min=invoer.interval_min,
            aantal_intervallen=0,
            kolommen=[],
            metadata={"reden": "weerpakket ontbreekt"},
            ontbrekende_behoeften=(WEERPAKKET_NAAM,),
        )
    if weerstations is None:
        raise ValueError(
            "weerdata is een landelijk (meerstations) pakket en vereist weerstations "
            "(stationscoördinaten): zie kern.model._interpoleer_weer_naar_locatie / kern.geo")

    # Tijd-as: triviale berekening, maar wel het aangewezen punt om het cache-
    # protocol te demonstreren (§4): bij herhaalde runs met hetzelfde jaar/
    # interval/tijdzone (bv. scenario's naast elkaar in een schil) hoeft de
    # tijd-as niet opnieuw opgebouwd te worden. De kern kent geen opslagvorm:
    # ``cache`` is een structureel Protocol (``kern.cache.Cache``); de schil
    # levert de implementatie.
    cache_sleutel_tijdas = f"tijdas:{invoer.kalenderjaar}:{invoer.interval_min}:{invoer.tijdzone__str}"
    index = cache.haal_op(cache_sleutel_tijdas) if cache is not None else None
    if index is None:
        meld(Voortgang("tijd-as", f"tijd-as opbouwen voor {invoer.kalenderjaar}"))
        index = bouw_tijd_as(invoer.kalenderjaar, invoer.interval_min, invoer.tijdzone__str).index
        if cache is not None:
            cache.zet(cache_sleutel_tijdas, index)
    else:
        meld(Voortgang("tijd-as", f"tijd-as uit cache ({invoer.kalenderjaar})"))
    n = len(index)

    meld(Voortgang(
        "weer",
        f"landelijk weerpakket ({weerdata.columns.get_level_values(1).nunique()} stations) "
        f"interpoleren naar locatie ({invoer.locatie_lat__degN:.4f}, {invoer.locatie_lon__degE:.4f})",
    ))
    weer_op_locatie = _interpoleer_weer_naar_locatie(
        weerdata, weerstations, invoer.locatie_lat__degN, invoer.locatie_lon__degE)

    meld(Voortgang("weer", "weerpakket uitlijnen op de tijd-as"))
    weer_uitgelijnd = _reindex_naar_tijdas(weer_op_locatie, index)
    temperatuur__degC = weer_uitgelijnd[WEERKOLOM_TEMPERATUUR].to_numpy(dtype=float)
    instraling__W_m_2 = weer_uitgelijnd[WEERKOLOM_STRALING].to_numpy(dtype=float)

    kolommen: dict[str, pd.Series] = {}

    pv_ac__W = pd.Series(0.0, index=index, name="pv_ac__W")
    if invoer.pv_toevoegen__bool:
        meld(Voortgang("pv", "PV-opbrengst berekenen (zonpositie → POA → DC → AC)", aandeel__0=0.0))
        pv_ac__W = pv_ac_vermogen__W(
            index, instraling__W_m_2, temperatuur__degC,
            invoer.locatie_lat__degN, invoer.locatie_lon__degE,
            invoer.pv_velden, invoer.pv_vermogen_per_paneel__Wp,
            invoer.pv_omvormer_capaciteit__W, invoer.pv_eta_omvormer__W0,
            invoer.pv_systeemverlies__0,
        )
        meld(Voortgang("pv", f"PV klaar: jaaropbrengst {pv_ac__W.sum() * invoer.interval_min / 60000:.0f} kWh",
                        aandeel__0=1.0))

        # Waarschuwing: de omvormer clipt structureel (§4-eis: minstens één waarschuwing).
        daglicht = instraling__W_m_2 > 0
        if daglicht.any():
            piekvermogen_dc_schatting__W = pv_ac__W / max(invoer.pv_eta_omvormer__W0, 1e-9)
            geclipt = (piekvermogen_dc_schatting__W >= invoer.pv_omvormer_capaciteit__W * 0.999) & daglicht
            aandeel_geclipt__0 = geclipt.sum() / daglicht.sum()
            if aandeel_geclipt__0 > CLIPPING_WAARSCHUWING_DREMPEL__0:
                meld(Voortgang(
                    "pv",
                    f"omvormer clipt op {aandeel_geclipt__0:.1%} van de daglicht-intervallen: "
                    f"omvormercapaciteit ({invoer.pv_omvormer_capaciteit__W:.0f} W) is klein "
                    "t.o.v. het paneelveld",
                    ernst="waarschuwing",
                ))
    kolommen["pv_ac__W"] = pv_ac__W

    if gemeten_basislast__W is not None:
        meld(Voortgang("basislast", "gemeten basislast gebruikt (geen terugval nodig)"))
        basislast__W = _reindex_naar_tijdas(gemeten_basislast__W, index)
    else:
        meld(Voortgang("basislast", "geen gemeten basislast: synthetisch profiel gebruikt (terugval)"))
        basislast__W = _synthetisch_basislastprofiel__W(index, invoer.interval_min,
                                                          invoer.basislast_jaarverbruik__kWh)
    kolommen["basislast__W"] = basislast__W

    status: str = "voltooid"
    if invoer.batterij_toevoegen__bool:
        prijs_uitgelijnd = (_reindex_naar_tijdas(prijsdata__EUR_kWh, index)
                            if prijsdata__EUR_kWh is not None else None)
        meld(Voortgang("batterij", "batterij simuleren (SoC-model)", aandeel__0=0.0))
        batterij_uitkomst, verwerkt = simuleer_batterij(
            pv_ac__W, basislast__W, invoer.interval_min, invoer.batterij,
            prijs__EUR_kWh=prijs_uitgelijnd, annuleer=annuleer,
            annuleer_elke_n=ANNULERING_POLL_INTERVAL,
        )
        kolommen["soc__0"] = batterij_uitkomst.soc__0
        kolommen["batterij_laad__W"] = batterij_uitkomst.laadvermogen__W
        kolommen["batterij_ontlaad__W"] = batterij_uitkomst.ontlaadvermogen__W
        kolommen["net_afname__W"] = batterij_uitkomst.net_afname__W
        if verwerkt < n:
            status = "geannuleerd"
            meld(Voortgang("batterij", f"geannuleerd na {verwerkt}/{n} intervallen", ernst="waarschuwing"))
            index = index[:verwerkt]
            kolommen = {naam: reeks.iloc[:verwerkt] for naam, reeks in kolommen.items()}
        else:
            meld(Voortgang("batterij", "batterij klaar", aandeel__0=1.0))
    else:
        kolommen["net_afname__W"] = basislast__W - pv_ac__W

    intervallen = pd.DataFrame(kolommen, index=index)
    intervallen.index.name = "tijdstip"

    if status == "geannuleerd":
        samenvatting = pd.DataFrame()
    else:
        samenvatting = intervallen.describe().reset_index(names="statistiek")

    meld(Voortgang("gereed", f"simulatie {status}", aandeel__0=1.0))

    return SimulatieUitvoer(
        contract_versie=CONTRACT_VERSIE,
        status__cat=status,
        intervallen=intervallen,
        samenvatting=samenvatting,
        kalenderjaar=invoer.kalenderjaar,
        interval_min=invoer.interval_min,
        aantal_intervallen=len(index),
        kolommen=list(intervallen.columns),
        metadata={
            "locatie_lat__degN": invoer.locatie_lat__degN,
            "locatie_lon__degE": invoer.locatie_lon__degE,
            "weerstations_aantal": int(weerdata.columns.get_level_values(1).nunique()),
            "pv_toevoegen__bool": invoer.pv_toevoegen__bool,
            "batterij_toevoegen__bool": invoer.batterij_toevoegen__bool,
            "behoefteplan_pakketten": [p.naam__str for p in plan.pakketbehoeften],
        },
    )
