# SPDX-License-Identifier: EUPL-1.2
"""
batterij.py: SoC-model van de thuisbatterijlaag.

Sterk vereenvoudigd ten opzichte van een echt EV-laadmodel (zie het
ontwerpdocument §3.3): geen ritprofiel, geen temperatuurafhankelijk verbruik,
geen noodrit-reserve. Wat overblijft is precies genoeg om **toestand die door
de tijd draagt** te demonstreren: de ladingstoestand (SoC) van interval tot
interval, en twee stuurregels.

Energiebalans (het invariant dat de tests vastpinnen): alle energie die de
batterij in gaat, komt er weer uit, op het retourrendement na. Er verdwijnt
geen energie anderszins, geen zelfontlading, geen lekverliezen.

Stuurregels
-----------
* ``eigen_verbruik`` : laad met PV-overschot (PV > vraag), ontlaad bij een
  PV-tekort (vraag > PV). Doel: zo min mogelijk van het net afnemen/terug-
  leveren.
* ``prijssignaal``   : laad wanneer de prijs onder de mediaan van het jaar
  ligt én er nog laadruimte is; ontlaad wanneer de prijs erboven ligt én er
  vraag is. De mediaan is een jaargrootheid: bekend zodra de prijsreeks
  binnen is, dus dit blijft, net als de rest van de kern, deterministisch en
  in één keer berekenbaar (geen per-interval optimalisatie, geen scipy).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .parameters import BatterijParameters


@dataclass(frozen=True)
class BatterijUitkomst:
    """Resultaat van de batterijsimulatie, als tijdreeksen op dezelfde index."""
    soc__0: pd.Series
    laadvermogen__W: pd.Series      # positief = laden (energie in de batterij)
    ontlaadvermogen__W: pd.Series   # positief = ontladen (energie uit de batterij)
    net_afname__W: pd.Series        # vraag die overblijft na PV + batterij (kan negatief = teruglevering)


def _stuursignaal_eigen_verbruik(pv_ac__W: np.ndarray, vraag__W: np.ndarray) -> np.ndarray:
    """Gewenst batterijvermogen per interval: positief = laadwens, negatief = ontlaadwens.

    Gebaseerd op het PV-overschot/-tekort van dát interval (vraag - PV): een
    overschot (PV > vraag) is een laadwens, een tekort is een ontlaadwens.
    """
    overschot__W = pv_ac__W - vraag__W
    return overschot__W  # >0 laadwens, <0 ontlaadwens (grootte = |waarde|)


def _stuursignaal_prijssignaal(prijs__EUR_kWh: np.ndarray, vraag__W: np.ndarray,
                                laadvermogen__W: float, ontlaadvermogen__W: float) -> np.ndarray:
    """Gewenst batterijvermogen per interval op grond van een prijssignaal.

    Laad voluit bij een prijs onder de mediaan van de aangeleverde reeks,
    ontlaad voluit (tot aan de actuele vraag) bij een prijs erboven. De
    mediaan is een vaste, uit de volledige jaarreeks afgeleide drempel;
    er is geen per-interval optimalisatie.
    """
    drempel__EUR_kWh = np.median(prijs__EUR_kWh)
    goedkoop = prijs__EUR_kWh <= drempel__EUR_kWh
    signaal = np.where(goedkoop, laadvermogen__W, -np.minimum(ontlaadvermogen__W, vraag__W))
    return signaal


def simuleer_batterij(
    pv_ac__W: pd.Series,
    vraag__W: pd.Series,
    interval_min: int,
    params: BatterijParameters,
    prijs__EUR_kWh: pd.Series | None = None,
    annuleer: Callable[[], bool] | None = None,
    annuleer_elke_n: int = 500,
) -> tuple[BatterijUitkomst, int]:
    """Simuleer de thuisbatterij interval-voor-interval (toestand draagt door de tijd).

    Dit is het **annuleringspunt** van de kern (§4.1 van het ontwerp): de
    batterijlaag is de enige laag die van interval tot interval toestand
    (SoC) doordraagt en dus niet zomaar in stukjes te knippen valt met een
    losse aanroep per interval. Elke ``annuleer_elke_n`` intervallen wordt
    ``annuleer()`` gepolld; geeft die ``True``, dan stopt de lus direct en
    geeft deze functie het aantal verwérkte intervallen terug, korter dan de
    volledige as. De aanroeper (``kern.model.simuleer``) zet dat om in een
    ``SimulatieUitvoer`` met ``status__cat == "geannuleerd"``, geen exception.

    Parameters
    ----------
    pv_ac__W        : PV-productie op dezelfde tijd-as als ``vraag__W``.
    vraag__W        : huishoudelijke vraag (exclusief batterij), zelfde as.
    interval_min    : intervallengte in minuten (voor de W → kWh-omrekening).
    params          : batterijparameters, zie ``kern.parameters.BatterijParameters``.
    prijs__EUR_kWh  : alleen nodig bij ``stuurregel__cat == "prijssignaal"``.
    annuleer        : callable zonder argumenten; ``True`` betekent "stop nu".
    annuleer_elke_n : pollfrequentie (in intervallen) van ``annuleer``.

    Returns
    -------
    (BatterijUitkomst, aantal_verwerkte_intervallen): het tweede element is
    gelijk aan ``len(pv_ac__W)`` tenzij er geannuleerd is.
    """
    n = len(pv_ac__W)
    uur_per_interval = interval_min / 60.0
    capaciteit__kWh = params.capaciteit__kWh

    pv = pv_ac__W.to_numpy(dtype=float)
    vraag = vraag__W.to_numpy(dtype=float)

    if params.stuurregel__cat == "eigen_verbruik":
        signaal__W = _stuursignaal_eigen_verbruik(pv, vraag)
    elif params.stuurregel__cat == "prijssignaal":
        if prijs__EUR_kWh is None:
            raise ValueError(
                "stuurregel 'prijssignaal' vereist een prijsreeks (prijs__EUR_kWh)")
        signaal__W = _stuursignaal_prijssignaal(
            prijs__EUR_kWh.to_numpy(dtype=float), vraag, params.laadvermogen__W,
            params.ontlaadvermogen__W)
    else:
        raise ValueError(f"onbekende stuurregel: {params.stuurregel__cat!r}")

    soc__0 = np.empty(n, dtype=float)
    laad__W = np.zeros(n, dtype=float)
    ontlaad__W = np.zeros(n, dtype=float)

    wortel_rendement__W0 = np.sqrt(params.retourrendement__W0)
    soc = params.soc_initieel__0

    verwerkt = n
    for i in range(n):
        if annuleer is not None and i > 0 and i % annuleer_elke_n == 0 and annuleer():
            verwerkt = i
            break
        gewenst__W = signaal__W[i]
        if gewenst__W >= 0:
            # Laadwens: begrensd door laadvermogen én door resterende capaciteit
            # tot soc_max, rekening houdend met het (halve) laadrendement.
            vermogen__W = min(gewenst__W, params.laadvermogen__W)
            ruimte__kWh = (params.soc_max__0 - soc) * capaciteit__kWh
            max_vermogen_door_ruimte__W = (ruimte__kWh / uur_per_interval) * 1000.0 / wortel_rendement__W0 \
                if uur_per_interval > 0 else float("inf")
            vermogen__W = max(0.0, min(vermogen__W, max_vermogen_door_ruimte__W))
            energie_in_batterij__kWh = vermogen__W * uur_per_interval / 1000.0 * wortel_rendement__W0
            soc = soc + energie_in_batterij__kWh / capaciteit__kWh
            laad__W[i] = vermogen__W
        else:
            # Ontlaadwens: begrensd door ontlaadvermogen én door resterende
            # energie tot soc_min.
            vermogen__W = min(-gewenst__W, params.ontlaadvermogen__W)
            beschikbaar__kWh = (soc - params.soc_min__0) * capaciteit__kWh
            max_vermogen_door_voorraad__W = (beschikbaar__kWh * wortel_rendement__W0 / uur_per_interval) * 1000.0 \
                if uur_per_interval > 0 else float("inf")
            vermogen__W = max(0.0, min(vermogen__W, max_vermogen_door_voorraad__W))
            energie_uit_batterij__kWh = vermogen__W * uur_per_interval / 1000.0 / wortel_rendement__W0
            soc = soc - energie_uit_batterij__kWh / capaciteit__kWh
            ontlaad__W[i] = vermogen__W

        soc__0[i] = np.clip(soc, params.soc_min__0, params.soc_max__0)
        soc = soc__0[i]

    soc__0 = soc__0[:verwerkt]
    laad__W = laad__W[:verwerkt]
    ontlaad__W = ontlaad__W[:verwerkt]
    net_afname__W = vraag[:verwerkt] - pv[:verwerkt] - laad__W + ontlaad__W

    idx = pv_ac__W.index[:verwerkt]
    uitkomst = BatterijUitkomst(
        soc__0=pd.Series(soc__0, index=idx, name="soc__0"),
        laadvermogen__W=pd.Series(laad__W, index=idx, name="batterij_laad__W"),
        ontlaadvermogen__W=pd.Series(ontlaad__W, index=idx, name="batterij_ontlaad__W"),
        net_afname__W=pd.Series(net_afname__W, index=idx, name="net_afname__W"),
    )
    return uitkomst, verwerkt
