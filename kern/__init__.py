# SPDX-License-Identifier: EUPL-1.2
"""
kern: de rekenkern van het voorbeeldrekenmodel.

Publieke API: ``simuleer(invoer) -> uitvoer`` (``kern.model``) en
``behoeften(invoer) -> BehoeftePlan`` (``kern.behoeften``). Zie het
ontwerpdocument voor de volledige motivatie per aspect.

De kern importeert uitsluitend ``numpy``, ``pandas`` en de standaardbibliotheek
(inclusief ``zoneinfo``). Geen scipy, geen netwerk, geen bestands-I/O; zie
``distributie/allowlist.py`` en de bijbehorende test.
"""
from __future__ import annotations

from .behoeften import Behoefte, BehoeftePlan, PakketBehoefte, behoeften
from .cache import Cache, GeheugenCache
from .model import simuleer
from .parameters import BatterijParameters, PVVeld, SimulatieParameters
from .uitvoer import CONTRACT_VERSIE, SimulatieUitvoer
from .voortgang import Melder, Voortgang, negeer_voortgang

__all__ = [
    "simuleer",
    "behoeften",
    "Behoefte",
    "BehoeftePlan",
    "PakketBehoefte",
    "Cache",
    "GeheugenCache",
    "BatterijParameters",
    "PVVeld",
    "SimulatieParameters",
    "CONTRACT_VERSIE",
    "SimulatieUitvoer",
    "Melder",
    "Voortgang",
    "negeer_voortgang",
]
