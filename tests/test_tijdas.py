# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de zomertijd-correcte tijd-as (kern/tijdas.py)."""
from __future__ import annotations

import pytest

from kern.tijdas import TOEGESTANE_INTERVALLEN_MIN, bouw_tijd_as


def test_kwartier_lengte_gewoon_jaar():
    """Kwartier over een gewoon jaar (365 dagen) = 35.040 intervallen (ontwerp §3.1)."""
    t = bouw_tijd_as(2023, 15)
    assert len(t) == 35_040


def test_uur_lengte_gewoon_jaar():
    t = bouw_tijd_as(2023, 60)
    assert len(t) == 8_760


def test_kwartier_lengte_schrikkeljaar():
    """2024 is een schrikkeljaar: 366 dagen × 4 kwartier/uur = 35.136."""
    t = bouw_tijd_as(2024, 15)
    assert len(t) == 35_136


def test_ongeldig_interval_geeft_valueerror():
    with pytest.raises(ValueError):
        bouw_tijd_as(2023, 20)


def test_alle_toegestane_intervallen_bouwen():
    for interval_min in TOEGESTANE_INTERVALLEN_MIN:
        t = bouw_tijd_as(2023, interval_min)
        assert len(t) > 0


def test_zomertijd_voorjaar_slaat_een_uur_over():
    """26 maart 2023: klok gaat om 02:00 naar 03:00: 02:00 lokale tijd bestaat niet."""
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    dag = idx[(idx.month == 3) & (idx.day == 26)]
    lokale_uren = sorted(dag.hour.tolist())
    assert lokale_uren == [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
    assert 2 not in lokale_uren


def test_zomertijd_najaar_herhaalt_een_uur():
    """29 oktober 2023: klok gaat om 03:00 terug naar 02:00: 02:00 komt twee keer voor."""
    t = bouw_tijd_as(2023, 60)
    idx = t.index
    dag = idx[(idx.month == 10) & (idx.day == 29)]
    assert len(dag) == 25  # één uur extra t.o.v. een gewone dag
    twee_uur = dag[dag.hour == 2]
    assert len(twee_uur) == 2
    # de twee instanties zijn verschillende UTC-momenten (anders zou het geen
    # echte klokherhaling zijn, maar een dubbele rij).
    assert twee_uur[0].utcoffset() != twee_uur[1].utcoffset()


def test_jaargrenzen_kloppen():
    t = bouw_tijd_as(2023, 60)
    assert t.index[0] == pytest_hulp_timestamp(2023, 1, 1)
    # laatste interval is vóór 1 jan 00:00 van het jaar erna (exclusief eindpunt)
    assert t.index[-1] < pytest_hulp_timestamp(2024, 1, 1)


def pytest_hulp_timestamp(jaar, maand, dag):
    import pandas as pd
    from zoneinfo import ZoneInfo
    return pd.Timestamp(year=jaar, month=maand, day=dag, tz=ZoneInfo("Europe/Amsterdam"))
