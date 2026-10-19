# SPDX-License-Identifier: EUPL-1.2
"""
test_allowlist.py: bewaakt dat ``kern/`` alleen toegestane afhankelijkheden
importeert (zie ``allowlist.py``).

Dit is de test uit ontwerpdocument §7: een verboden import (scipy, requests,
pytz, os-bestands-I/O, ...) moet hier een **rode test** geven, niet pas een
mysterie in de browser. We ontleden elk bestand in ``kern/`` met ``ast``
(niet door het te importeren: dat zou een ontbrekende afhankelijkheid zelf al
laten crashen vóór de test iets kan zeggen) en controleren elke absolute
top-level import tegen de allowlist. Relatieve imports (``from . import x``)
zijn per definitie intern aan het pakket en worden niet getoetst; omdat
``kern/`` een plat pakket is (geen subpakketten), is "elk bestand in de map"
hier gelijk aan de volledige transitieve afsluiting van ``import kern``.
"""
from __future__ import annotations

import ast
from pathlib import Path

from allowlist import TOEGESTANE_MODULES, kernmap


def _top_level_imports(pad: Path) -> set[str]:
    """Alle absolute top-level modulenamen die dit bestand importeert."""
    boom = ast.parse(pad.read_text(encoding="utf-8"), filename=str(pad))
    namen: set[str] = set()
    for node in ast.walk(boom):
        if isinstance(node, ast.Import):
            for alias in node.names:
                namen.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relatieve import: intern aan kern/, niet toetsen
            if node.module:
                namen.add(node.module.split(".")[0])
    return namen


def test_allowlist_dekt_alle_imports_in_kern():
    """Elke absolute import in kern/*.py moet in TOEGESTANE_MODULES staan."""
    kern = kernmap()
    bestanden = sorted(kern.glob("*.py"))
    assert bestanden, f"geen .py-bestanden gevonden in {kern}"

    overtredingen: dict[str, set[str]] = {}
    for bestand in bestanden:
        gebruikt = _top_level_imports(bestand)
        verboden = gebruikt - TOEGESTANE_MODULES
        if verboden:
            overtredingen[bestand.name] = verboden

    assert not overtredingen, (
        "deze bestanden in kern/ importeren iets buiten de allowlist "
        f"(zie distributie/allowlist.py): {overtredingen}")


def test_kernmap_bestaat_en_is_niet_leeg():
    """Sanity check: het pad dat de test dekt, bestaat écht."""
    kern = kernmap()
    assert kern.is_dir(), f"kernmap() wijst naar een niet-bestaande map: {kern}"
    assert list(kern.glob("*.py")), f"geen .py-bestanden in {kern}"


def test_geen_uitdrukkelijk_verboden_module_in_allowlist():
    """De allowlist zelf mag nooit per ongeluk een verboden module bevatten."""
    from allowlist import UITDRUKKELIJK_VERBODEN
    overlap = TOEGESTANE_MODULES & UITDRUKKELIJK_VERBODEN
    assert not overlap, f"allowlist en verbodenlijst overlappen: {overlap}"


def test_top_level_imports_ziet_een_scipy_import(tmp_path):
    """Regressietoets voor de kern-eis achter deze module: ``kern/geo.py``
    lost dezelfde wiskunde als ``scipy.interpolate.RBFInterpolator`` zelf op,
    juist om scipy uit ``kern/`` te kunnen weren (zie de moduledocstring van
    ``kern.geo``). We zetten hiervoor geen scipy-import in de echte ``kern/``
    (dat zou deze hele testsuite meteen rood maken); in plaats daarvan
    bevestigen we hier direct dat het detectiemechanisme, ``_top_level_imports``,
    zo'n import ook werkelijk ziet zodra hij ergens in ``kern/`` zou belanden,
    en dat ``scipy`` niet stiekem al in de allowlist staat.
    """
    bestand = tmp_path / "zou_niet_mogen.py"
    bestand.write_text("import scipy.interpolate\n\ndef iets():\n    return scipy.interpolate.RBFInterpolator\n",
                        encoding="utf-8")
    gevonden = _top_level_imports(bestand)
    assert "scipy" in gevonden
    assert "scipy" not in TOEGESTANE_MODULES, (
        "scipy staat op de allowlist: dan zou test_allowlist_dekt_alle_imports_in_kern "
        "een scipy-import in kern/ juist NIET meer vangen")
