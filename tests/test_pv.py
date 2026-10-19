# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de PV-keten (kern/pv.py): zonpositie → POA → DC → AC."""
from __future__ import annotations

import numpy as np

from kern.parameters import PVVeld
from kern.pv import pv_ac_vermogen__W, splits_diffuus_erbs, zonpositie
from kern.tijdas import bouw_tijd_as

LAT__DEGN = 52.1326
LON__DEGE = 5.2913


def _eenvoudig_weer(index):
    zon = zonpositie(index, LAT__DEGN, LON__DEGE)
    el = np.clip(zon.elevatie__deg, 0.0, 90.0)
    instraling__W_m_2 = np.clip(np.sin(np.radians(el)) * 700.0, 0.0, None)
    temperatuur__degC = np.full(len(index), 15.0)
    return instraling__W_m_2, temperatuur__degC


def test_pv_nul_in_de_nacht():
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    instraling__W_m_2, temp = _eenvoudig_weer(idx)
    pac = pv_ac_vermogen__W(idx, instraling__W_m_2, temp, LAT__DEGN, LON__DEGE,
                             (PVVeld(aantal_panelen__0=12),), 440.0, 5000.0, 0.97, 0.14)
    nacht = idx.hour.isin([1, 2, 3])
    assert (pac[nacht] == 0.0).all()


def test_pv_positief_rond_zonnewende():
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    instraling__W_m_2, temp = _eenvoudig_weer(idx)
    pac = pv_ac_vermogen__W(idx, instraling__W_m_2, temp, LAT__DEGN, LON__DEGE,
                             (PVVeld(aantal_panelen__0=12),), 440.0, 5000.0, 0.97, 0.14)
    zomerzonnewende_middag = pac[(idx.month == 6) & (idx.day == 21) & (idx.hour == 12)]
    winterzonnewende_middag = pac[(idx.month == 12) & (idx.day == 21) & (idx.hour == 12)]
    assert (zomerzonnewende_middag > 0).all()
    assert (winterzonnewende_middag > 0).all()


def test_pv_nooit_negatief():
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    instraling__W_m_2, temp = _eenvoudig_weer(idx)
    pac = pv_ac_vermogen__W(idx, instraling__W_m_2, temp, LAT__DEGN, LON__DEGE,
                             (PVVeld(aantal_panelen__0=12),), 440.0, 5000.0, 0.97, 0.14)
    assert (pac >= 0.0).all()


def test_omvormer_clipt_niet_boven_capaciteit():
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    # Overdreven hoge instraling om clipping te forceren.
    instraling__W_m_2 = np.full(len(idx), 1200.0)
    zon = zonpositie(idx, LAT__DEGN, LON__DEGE)
    instraling__W_m_2 = np.where(zon.elevatie__deg > 0, instraling__W_m_2, 0.0)
    temp = np.full(len(idx), 15.0)
    omvormer_capaciteit__W = 2000.0
    pac = pv_ac_vermogen__W(idx, instraling__W_m_2, temp, LAT__DEGN, LON__DEGE,
                             (PVVeld(aantal_panelen__0=40),), 440.0, omvormer_capaciteit__W, 0.97, 0.14)
    assert pac.max() <= omvormer_capaciteit__W + 1e-6


def test_zonpositie_hoogte_binnen_bereik():
    t = bouw_tijd_as(2023, 60)
    zon = zonpositie(t.index, LAT__DEGN, LON__DEGE)
    assert (zon.elevatie__deg >= -90.0).all()
    assert (zon.elevatie__deg <= 90.0).all()
    assert (zon.azimut__deg >= 0.0).all()
    assert (zon.azimut__deg < 360.0).all()


def test_erbs_diffuus_niet_groter_dan_globaal():
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    instraling__W_m_2, _ = _eenvoudig_weer(idx)
    zon = zonpositie(idx, LAT__DEGN, LON__DEGE)
    _, diffuus__W_m_2 = splits_diffuus_erbs(instraling__W_m_2, zon)
    assert (diffuus__W_m_2 <= instraling__W_m_2 + 1e-6).all()
    assert (diffuus__W_m_2 >= 0.0).all()
