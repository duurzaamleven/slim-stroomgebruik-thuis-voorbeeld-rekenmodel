# SPDX-License-Identifier: EUPL-1.2
"""Determinisme-eis (ontwerpdocument §4): gelijke invoer → bit-identieke uitvoer.

Dit is geen nettigheid maar een eis (§5.5): zonder dit flikkert een progressief
verfijnend antwoord in de schil. Deze test pint het vast op het niveau van de
publieke ``simuleer``-aanroep.
"""
from __future__ import annotations

import pandas as pd

from kern.model import simuleer


def test_simuleer_is_deterministisch(standaard_invoer, weerdata_2023, weerstations):
    u1 = simuleer(standaard_invoer, weerdata=weerdata_2023, weerstations=weerstations)
    u2 = simuleer(standaard_invoer, weerdata=weerdata_2023, weerstations=weerstations)

    assert u1.status__cat == u2.status__cat == "voltooid"
    pd.testing.assert_frame_equal(u1.intervallen, u2.intervallen)
    pd.testing.assert_frame_equal(u1.samenvatting, u2.samenvatting)
    assert u1.metadata == u2.metadata
    assert u1.kolommen == u2.kolommen
    assert u1.contract_versie == u2.contract_versie


def test_simuleer_is_deterministisch_met_prijssignaal(standaard_invoer, weerdata_2023, weerstations):
    from dataclasses import replace
    from kern.parameters import BatterijParameters

    invoer = replace(standaard_invoer,
                      batterij=BatterijParameters(stuurregel__cat="prijssignaal"))
    idx = weerdata_2023.index
    import numpy as np
    prijs = pd.Series(0.15 + 0.05 * np.sin(np.linspace(0, 40 * np.pi, len(idx))), index=idx)

    u1 = simuleer(invoer, weerdata=weerdata_2023, weerstations=weerstations, prijsdata__EUR_kWh=prijs)
    u2 = simuleer(invoer, weerdata=weerdata_2023, weerstations=weerstations, prijsdata__EUR_kWh=prijs)
    pd.testing.assert_frame_equal(u1.intervallen, u2.intervallen)


def test_verschillende_invoer_geeft_niet_toevallig_dezelfde_uitvoer(standaard_invoer, weerdata_2023, weerstations):
    """Sanity check op de determinisme-test zelf: verschillende invoer moet ook
    echt verschillende uitvoer geven (anders zou de vorige test niets bewijzen)."""
    from dataclasses import replace

    invoer_anders = replace(standaard_invoer, basislast_jaarverbruik__kWh=9000.0)
    u1 = simuleer(standaard_invoer, weerdata=weerdata_2023, weerstations=weerstations)
    u2 = simuleer(invoer_anders, weerdata=weerdata_2023, weerstations=weerstations)
    assert not u1.intervallen["basislast__W"].equals(u2.intervallen["basislast__W"])
