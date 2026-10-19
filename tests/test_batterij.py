# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de thuisbatterijlaag (kern/batterij.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kern.batterij import simuleer_batterij
from kern.parameters import BatterijParameters


def _maak_reeksen(n=24 * 10, seed=0):
    idx = pd.date_range("2023-01-01", periods=n, freq="h", tz="Europe/Amsterdam")
    rng = np.random.default_rng(seed)
    pv__W = pd.Series(np.clip(np.sin(np.linspace(0, 10 * np.pi, n)) * 2500, 0, None) +
                       rng.normal(0, 50, n).clip(min=0), index=idx)
    vraag__W = pd.Series(400 + 250 * np.sin(np.linspace(0, 20 * np.pi, n)) + rng.normal(0, 20, n),
                          index=idx)
    return pv__W, vraag__W.clip(lower=50)


def test_energiebalans_eigen_verbruik():
    """Alle energie die erin gaat, komt eruit: op het retourrendement na."""
    pv__W, vraag__W = _maak_reeksen()
    params = BatterijParameters(
        capaciteit__kWh=8.0, laadvermogen__W=3000.0, ontlaadvermogen__W=3000.0,
        soc_min__0=0.1, soc_max__0=0.9, soc_initieel__0=0.5, retourrendement__W0=0.9,
        stuurregel__cat="eigen_verbruik",
    )
    uitkomst, verwerkt = simuleer_batterij(pv__W, vraag__W, 60, params)
    assert verwerkt == len(pv__W)

    soc_start__kWh = params.soc_initieel__0 * params.capaciteit__kWh
    soc_eind__kWh = uitkomst.soc__0.iloc[-1] * params.capaciteit__kWh
    delta_soc__kWh = soc_eind__kWh - soc_start__kWh

    energie_in__kWh = uitkomst.laadvermogen__W.sum() / 1000.0
    energie_uit__kWh = uitkomst.ontlaadvermogen__W.sum() / 1000.0
    wortel_eta = np.sqrt(params.retourrendement__W0)
    verwachte_delta__kWh = energie_in__kWh * wortel_eta - energie_uit__kWh / wortel_eta

    assert delta_soc__kWh == pytest.approx(verwachte_delta__kWh, abs=1e-6)


def test_energiebalans_prijssignaal():
    pv__W, vraag__W = _maak_reeksen(seed=1)
    idx = pv__W.index
    prijs__EUR_kWh = pd.Series(0.15 + 0.10 * np.sin(np.linspace(0, 6 * np.pi, len(idx))), index=idx)
    params = BatterijParameters(
        capaciteit__kWh=10.0, laadvermogen__W=2500.0, ontlaadvermogen__W=2500.0,
        soc_min__0=0.05, soc_max__0=0.95, soc_initieel__0=0.4, retourrendement__W0=0.85,
        stuurregel__cat="prijssignaal",
    )
    uitkomst, verwerkt = simuleer_batterij(pv__W, vraag__W, 60, params, prijs__EUR_kWh=prijs__EUR_kWh)
    assert verwerkt == len(pv__W)

    soc_start__kWh = params.soc_initieel__0 * params.capaciteit__kWh
    soc_eind__kWh = uitkomst.soc__0.iloc[-1] * params.capaciteit__kWh
    delta_soc__kWh = soc_eind__kWh - soc_start__kWh
    energie_in__kWh = uitkomst.laadvermogen__W.sum() / 1000.0
    energie_uit__kWh = uitkomst.ontlaadvermogen__W.sum() / 1000.0
    wortel_eta = np.sqrt(params.retourrendement__W0)
    verwachte_delta__kWh = energie_in__kWh * wortel_eta - energie_uit__kWh / wortel_eta
    assert delta_soc__kWh == pytest.approx(verwachte_delta__kWh, abs=1e-6)

    # Laadt de batterij ook echt, en ontlaadt hij ook echt (geen no-op stuurregel).
    assert energie_in__kWh > 0
    assert energie_uit__kWh > 0


def test_soc_blijft_binnen_grenzen():
    pv__W, vraag__W = _maak_reeksen(n=24 * 30, seed=2)
    params = BatterijParameters(soc_min__0=0.15, soc_max__0=0.9)
    uitkomst, _ = simuleer_batterij(pv__W, vraag__W, 60, params)
    assert (uitkomst.soc__0 >= params.soc_min__0 - 1e-9).all()
    assert (uitkomst.soc__0 <= params.soc_max__0 + 1e-9).all()


def test_prijssignaal_zonder_prijsreeks_geeft_fout():
    pv__W, vraag__W = _maak_reeksen()
    params = BatterijParameters(stuurregel__cat="prijssignaal")
    with pytest.raises(ValueError):
        simuleer_batterij(pv__W, vraag__W, 60, params, prijs__EUR_kWh=None)
