# SPDX-License-Identifier: EUPL-1.2
"""
allowlist.py: de toegestane afhankelijkheden van de rekenkern.

Ontwerpdocument §7: "neem de distributie/-gedachte over": een **allowlist**,
geen denylist (zie het architectuurprincipe uit de echte repo: een vergeten
verboden import faalt zo *zichtbaar* in plaats van stil in de browser). Deze
module bevat alleen de lijst; de test die de transitieve afsluiting van
``kern/`` ertegen controleert staat in ``test_allowlist.py`` ernaast.

Waarom dit ertoe doet: de kern moet ooit als Pyodide/WASM-bundel kunnen
draaien. ``scipy`` is loodzwaar in die context, ``pytz`` opent bij het
starten honderden bestanden (zie het ontwerpdocument §3.1), en netwerk- of
bestands-I/O kan in een worker sowieso niet zomaar. Een import die daarbuiten
valt, moet een **rode test** geven op de plek waar hij wordt toegevoegd, niet
pas een mysterie in de browser.
"""
from __future__ import annotations

from pathlib import Path

#: Top-level modulenamen die de rekenkern (``kern/``) mag importeren.
#: Alles wat hier niet in staat, is verboden, ook als het "maar een klein
#: importje" is. Zie de moduledocstring voor de reden.
TOEGESTANE_MODULES: frozenset[str] = frozenset({
    # standaardbibliotheek, bewust beperkt
    "__future__",
    "dataclasses",
    "typing",
    "zoneinfo",
    "datetime",
    "math",
    "functools",
    "itertools",
    "abc",
    "collections",
    "enum",
    # rekenen
    "numpy",
    "pandas",
})

#: Uitdrukkelijk NIET toegestaan (ter documentatie; de test controleert dit
#: niet expliciet af: alles wat niet in TOEGESTANE_MODULES staat, faalt al).
UITDRUKKELIJK_VERBODEN = frozenset({
    "scipy",       # te zwaar voor een WASM-bundel
    "pytz",        # opent honderden bestanden bij import (zie ontwerp §3.1); gebruik zoneinfo
    "requests",    # netwerk: de kern is acquisitievrij
    "urllib",      # idem
    "http",        # idem
    "os",          # bestands-I/O hoort in de schil, niet in de kern
    "pathlib",     # idem
    "io",          # idem
})


def kernmap() -> Path:
    """Absoluut pad naar de ``kern/``-map, uitgaande van deze bestandslocatie."""
    return Path(__file__).resolve().parent.parent / "kern"
