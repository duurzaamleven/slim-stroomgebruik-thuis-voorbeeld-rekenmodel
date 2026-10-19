# SPDX-License-Identifier: EUPL-1.2
"""
voortgang.py: platformonafhankelijk voortgangscontract van de rekenkern.

De rekenkern (``kern/model.py``) meldt voortgang als **semantische events**: wát
er gebeurt (fase, boodschap, ernst, optioneel een aandeel), niet hóe dat getoond
wordt. Elke schil (CLI nu, browser later) levert een ``Melder`` die zelf beslist
over weergave en throttling. Zo bevat de kern geen enkele platformaanname: geen
tijdstempel, geen opmaak, geen UI-specifieke vlag.

Dit is bewust dezelfde vorm als in het echte simulatiemodel van Kenniscentrum Duurzaam Leven
(zie het ontwerpdocument, §4): een browser-adapter kan een ``Voortgang``-event
bijvoorbeeld vertalen naar een ``postMessage`` vanuit een Pyodide-worker, een
statusregel met kleur op grond van ``ernst``, en een voortgangsbalk gevoed door
``aandeel``. Throttling gebeurt dan schilzijdig; de kern hoeft daar niets van te
weten.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

# Ernst van een melding. Bewust klein gehouden.
Ernst = Literal["info", "waarschuwing"]


@dataclass(frozen=True)
class Voortgang:
    """
    Eén voortgangsevent uit de rekenkern.

    Attributen
    ----------
    fase      : welk onderdeel bezig is, bv. "tijd-as", "pv", "batterij".
    boodschap : vrije, voor mensen leesbare tekst (zonder tijdstempel/opmaak).
    ernst     : "info" (standaard) of "waarschuwing".
    aandeel__0: voortgang binnen de fase als fractie in [0, 1], of None als
                onbekend.
    """
    fase: str
    boodschap: str
    ernst: Ernst = "info"
    aandeel__0: float | None = None


# Een melder ontvangt één Voortgang-event en doet er platformspecifiek iets mee.
Melder = Callable[[Voortgang], None]


def negeer_voortgang(_: Voortgang) -> None:
    """Standaard stille melder (headless/notebook/test): doet niets."""
    return None
