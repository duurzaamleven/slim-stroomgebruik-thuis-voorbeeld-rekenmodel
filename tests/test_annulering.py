# SPDX-License-Identifier: EUPL-1.2
"""Annuleringspunt (ontwerpdocument §4.1): een langlopende run netjes afbreken."""
from __future__ import annotations

from kern.model import ANNULERING_POLL_INTERVAL, simuleer
from kern.uitvoer import CONTRACT_VERSIE


def test_annulering_geeft_status_geannuleerd_en_deelresultaat(standaard_invoer, weerdata_2023_kwartier,
                                                                weerstations):
    from dataclasses import replace

    invoer = replace(standaard_invoer, interval_min=15)

    aanroepen = {"n": 0}

    def annuleer():
        aanroepen["n"] += 1
        return aanroepen["n"] >= 2  # stop bij de tweede poll

    uitvoer = simuleer(invoer, weerdata=weerdata_2023_kwartier, weerstations=weerstations, annuleer=annuleer)

    assert uitvoer.status__cat == "geannuleerd"
    assert 0 < uitvoer.aantal_intervallen < len(weerdata_2023_kwartier)
    # De deelresultaten zijn intern consistent (geen NaN-staart, geen extra rijen).
    assert len(uitvoer.intervallen) == uitvoer.aantal_intervallen
    assert not uitvoer.intervallen.isna().any().any()
    assert uitvoer.contract_versie == CONTRACT_VERSIE


def test_annulering_die_nooit_afgaat_voltooit_normaal(standaard_invoer, weerdata_2023, weerstations):
    uitvoer = simuleer(standaard_invoer, weerdata=weerdata_2023, weerstations=weerstations, annuleer=lambda: False)
    assert uitvoer.status__cat == "voltooid"
    assert uitvoer.aantal_intervallen == len(weerdata_2023)


def test_annulering_zonder_batterij_heeft_geen_effect(standaard_invoer, weerdata_2023, weerstations):
    """Zonder batterijlaag is er (in deze toy) geen langlopende lus om af te
    breken: de aanroep moet dan gewoon normaal voltooien, niet crashen."""
    from dataclasses import replace

    invoer = replace(standaard_invoer, batterij_toevoegen__bool=False)
    uitvoer = simuleer(invoer, weerdata=weerdata_2023, weerstations=weerstations, annuleer=lambda: True)
    assert uitvoer.status__cat == "voltooid"


def test_poll_interval_is_positief():
    assert ANNULERING_POLL_INTERVAL > 0
