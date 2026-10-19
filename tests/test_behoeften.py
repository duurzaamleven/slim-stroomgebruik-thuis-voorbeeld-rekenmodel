# SPDX-License-Identifier: EUPL-1.2
"""Het behoefteplan is een pure functie van de parameters (ontwerpdocument §5)."""
from __future__ import annotations

from dataclasses import replace

from kern.behoeften import PRIJSPAKKET_NAAM, WEERPAKKET_NAAM, behoeften
from kern.model import simuleer
from kern.parameters import BatterijParameters


def test_behoeften_is_puur(standaard_invoer):
    """Twee aanroepen met dezelfde invoer geven hetzelfde plan, geen state, geen I/O."""
    plan1 = behoeften(standaard_invoer)
    plan2 = behoeften(standaard_invoer)
    assert plan1 == plan2


def test_weerpakket_is_altijd_verplicht(standaard_invoer):
    plan = behoeften(standaard_invoer)
    namen = [p.naam__str for p in plan.pakketbehoeften]
    assert WEERPAKKET_NAAM in namen


def test_prijspakket_alleen_bij_prijssignaal(standaard_invoer):
    plan_zonder = behoeften(standaard_invoer)
    namen_zonder = [p.naam__str for p in plan_zonder.pakketbehoeften]
    assert PRIJSPAKKET_NAAM not in namen_zonder

    invoer_met = replace(standaard_invoer, batterij=BatterijParameters(stuurregel__cat="prijssignaal"))
    plan_met = behoeften(invoer_met)
    namen_met = [p.naam__str for p in plan_met.pakketbehoeften]
    assert PRIJSPAKKET_NAAM in namen_met


def test_elke_behoefte_noemt_een_grootheid_nooit_een_kanaal(standaard_invoer):
    """Ontwerpregel §5.3: geen enkele grootheid__str mag een kanaalnaam bevatten."""
    verboden_kanaaltermen = ("p1", "homewizard", "edx", "oauth", "url", "http", "api")
    plan = behoeften(standaard_invoer)
    for b in plan.behoeften:
        laag = b.grootheid__str.lower()
        for term in verboden_kanaaltermen:
            assert term not in laag, f"{b.grootheid__str!r} lijkt een kanaal te noemen ({term})"


def test_elke_behoefte_heeft_vier_velden(standaard_invoer):
    plan = behoeften(standaard_invoer)
    for b in plan.behoeften:
        assert b.noodzaak__cat in ("verplicht", "verbetert")
        assert isinstance(b.terugval__str, str) and b.terugval__str
        assert 0.0 <= b.gewicht__0 <= 1.0


def test_batterijbehoefte_alleen_als_batterij_aan(standaard_invoer):
    plan_aan = behoeften(standaard_invoer)
    grootheden_aan = [b.grootheid__str for b in plan_aan.behoeften]
    assert "batterij_capaciteit_en_vermogen" in grootheden_aan

    invoer_uit = replace(standaard_invoer, batterij_toevoegen__bool=False)
    plan_uit = behoeften(invoer_uit)
    grootheden_uit = [b.grootheid__str for b in plan_uit.behoeften]
    assert "batterij_capaciteit_en_vermogen" not in grootheden_uit


def test_precies_een_verplicht_pakket_zonder_batterij_op_prijssignaal(standaard_invoer):
    """Ontwerp §5.7: er is precies één verplichte externe behoefte (het weer)
    zolang de batterij niet op een prijssignaal stuurt."""
    plan = behoeften(standaard_invoer)
    assert len(plan.pakketbehoeften) == 1
    verplichte_grootheden = [b for b in plan.behoeften if b.noodzaak__cat == "verplicht"]
    # De enige "verplichte" grootheid is er één die hoort bij een ingeschakelde
    # laag (batterij), niet bij een externe data-acquisitie.
    assert all(b.grootheid__str == "batterij_capaciteit_en_vermogen" for b in verplichte_grootheden)


def test_geen_verrassing_halverwege(standaard_invoer):
    """Ontwerp §5.6: wat het behoefteplan vooraf als verplicht aanmerkt, is
    precies wat ``simuleer`` controleert vóór hij begint te rekenen: er is
    geen scenario waarin de kern *tijdens* het rekenen ontdekt dat er iets
    ontbreekt. Dat zou een fout in het plan zijn, geen geval om af te handelen.
    """
    plan = behoeften(standaard_invoer)
    verplichte_pakketten = [p.naam__str for p in plan.pakketbehoeften]
    assert verplichte_pakketten == [WEERPAKKET_NAAM]

    # Precies het pakket dat het plan verplicht noemt, ontbreekt hier, en de
    # kern moet dat direct en netjes melden, zonder een halve berekening.
    uitvoer = simuleer(standaard_invoer, weerdata=None)
    assert uitvoer.status__cat == "onvolledig"
    assert uitvoer.ontbrekende_behoeften == (WEERPAKKET_NAAM,)
    assert uitvoer.intervallen.empty
