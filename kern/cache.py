# SPDX-License-Identifier: EUPL-1.2
"""
cache.py: cache-protocol van de rekenkern.

Dit is precies het browserprobleem uit het ontwerpdocument (§4): bestand nu,
IndexedDB straks. De kern kent alleen een **structureel protocol** (``Cache``),
geen concrete implementatie. De schil levert die: een CLI-schil kan een map
met bestanden gebruiken, een browserschil IndexedDB, een testschil een dict.

De kern raakt zelf geen bestanden of netwerk aan: hij vraagt de cache om een
sleutel op te halen of weg te schrijven, en weet niet hoe dat gebeurt. Dat is
dezelfde scheiding als bij ``kern.behoeften``: de kern noemt wát hij nodig
heeft, nooit hóe of wáár dat wordt gehaald of bewaard.

Deze module gebruikt ``typing.Protocol`` (structureel typen): een klasse hoeft
niet van iets te erven om als ``Cache`` te gelden, ze moet alleen de juiste
methoden hebben.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    """Structureel protocol voor een sleutel/waarde-cache.

    Een implementatie mag alles doen wat achter deze drie methoden past: een
    JSON-bestand op schijf, een browsertabel, of: voor tests: een gewoon
    dict. De kern gebruikt de cache alleen om dubbel werk te vermijden (bv.
    een afgeleide berekening op het geïnjecteerde weerpakket); hij bevat zelf
    geen enkele aanname over de opslagvorm.
    """

    def haal_op(self, sleutel: str) -> Any | None:
        """Geef de gecachte waarde voor ``sleutel``, of ``None`` als die er niet is."""
        ...

    def zet(self, sleutel: str, waarde: Any) -> None:
        """Bewaar ``waarde`` onder ``sleutel``."""
        ...

    def bevat(self, sleutel: str) -> bool:
        """Zit ``sleutel`` in de cache?"""
        ...


class GeheugenCache:
    """Triviale in-memory referentie-implementatie van ``Cache``.

    Niet bedoeld voor productiegebruik (verdwijnt bij het einde van het
    proces): dient als standaardimplementatie voor tests en voor de
    CLI-schil, en als voorbeeld van hoe weinig een implementatie van dit
    protocol hoeft te bevatten.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def haal_op(self, sleutel: str) -> Any | None:
        return self._data.get(sleutel)

    def zet(self, sleutel: str, waarde: Any) -> None:
        self._data[sleutel] = waarde

    def bevat(self, sleutel: str) -> bool:
        return sleutel in self._data
