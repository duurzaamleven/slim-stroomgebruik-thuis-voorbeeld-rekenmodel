# SPDX-License-Identifier: EUPL-1.2
"""
geo.py: geospatiale interpolatie van een landelijk weerpakket, numpy-only.

Waarom deze module bestaat
---------------------------
Het weerpakket dat de kern binnenkrijgt is **landelijk**: alle KNMI-meetpunten
tegelijk, geen reeks per locatie. Dat is een bewuste privacykeuze van de
uitgever (zie ``kern/behoeften.py``): zou er per locatie een reeks klaarstaan,
dan zou het enkele feit dat een afnemer dát pakket ophaalt al een
locatiemelding zijn. De **afnemer** interpoleert daarom zelf, op zijn eigen
apparaat, naar zijn eigen ``lat__degN``/``lon__degE``. Deze module is die
interpolatiestap.

Ze doet dat met alleen ``numpy``: de rekenkern mag geen ``scipy`` importeren
(zie ``distributie/allowlist.py``), onder andere met het oog op een
toekomstige WASM/Pyodide-bundel waarin ``scipy`` te zwaar zou zijn.

Geen benadering, een herschrijving
-----------------------------------
Wat hier gebeurt is functioneel gelijk aan ``scipy.interpolate.RBFInterpolator``
in zijn standaardinstelling: kernel ``r**2 * log(r)`` (thin-plate-spline),
een polynoomterm van graad 1, ``smoothing=0``, alle stations meegenomen. Dat
stelsel wordt hier met de hand opgelost in plaats van via scipy aangeroepen:
het is dezelfde wiskundige functie, niet een nieuw of ander model.

⚠️ **Het belangrijkste inzicht.** De stationscoördinaten zijn voor elk
tijdstip en elke grootheid identiek, dus is ook het op te lossen stelsel
telkens identiek. Interpolatie naar één vaste doellocatie is daarmee een
**vaste lineaire combinatie** van de stationswaarden: er bestaat één
gewichtsvector ``w`` zodat ``waarde_op_doel = w @ stationswaarden``, voor elk
tijdstip en elke grootheid. Die ``w`` reken je precies één keer uit
(``geo_gewichten``); daarna is een heel jaar aan uurwaarden, voor elke
grootheid opnieuw, niets meer dan een matrixvermenigvuldiging
(``interpoleer``). Voor 22 landelijke stations en een heel jaar aan
weergrootheden scheelt dat vele duizenden losse RBF-oplossingen t.o.v. het
per-tijdstip-en-metriek opnieuw fitten dat ``RBFInterpolator`` zelf doet.

Het stelsel
-----------
Zadelpuntstelsel voor thin-plate-spline-RBF-interpolatie met een lineaire
polynoomterm erbij (nodig voor een goed-geconditioneerd, uniek oplosbaar
stelsel)::

    [ A    P ] [a]   [y]
    [ P^T  0 ] [b] = [0]

met ``A[i, j] = phi(afstand tussen station i en station j)``,
``P[i] = [1, lat_i, lon_i]`` en ``phi(r) = r**2 * log(r)`` (met de limiet
``phi(0) := 0``). De waarde op de doellocatie is dan
``phi_doel @ a + [1, lat*, lon*] @ b``. Omdat dat lineair is in de metingen
``y`` (het stelsel zelf hangt niet van ``y`` af), is er een rij te vinden in
de inverse van het stelsel die precies deze lineaire afbeelding is: de eerste
``n`` gewichten van ``solve(stelsel^T, rechterlid_doel)``.

**Afstandsmaat.** Euclidisch in graden (lat, lon), niet over de bol. Voor het
Nederlandse stationsnet (een paar honderd kilometer) is dat een te
verwaarlozen vereenvoudiging, en bovendien de conventie van de bron die deze
module vervangt (``scipy.interpolate.RBFInterpolator`` zonder eigen
afstandsmaat rekent ook gewoon euclidisch in de meegegeven coördinaten). Wie
dat verandert, verandert daarmee ook wát er precies wordt gereproduceerd.

Getoetst tegen scipy in ``tests/test_geo.py`` (verschil < 1e-9 over vele
willekeurige waardevectoren en doellocaties); dat is een test-afhankelijkheid,
geen kernafhankelijkheid (zie ``requirements-dev.txt``).
"""
from __future__ import annotations

import numpy as np

#: Minstens 3 stations nodig: de polynoomterm van graad 1 heeft drie vrije
#: coëfficiënten (``1``, ``lat``, ``lon``) en het stelsel moet daarvoor
#: eenduidig oplosbaar zijn.
_MIN_STATIONS = 3


def _tps_kernel__0(afstand__deg: np.ndarray) -> np.ndarray:
    """Thin-plate-spline-kernel ``phi(r) = r**2 * log(r)``, met ``phi(0) = 0``.

    ``r = 0`` geeft wiskundig een 0·(-inf)-onbepaaldheid waarvan de limiet 0
    is; we onderdrukken de bijbehorende numpy-waarschuwingen en vullen die
    limiet expliciet in, in plaats van op de float-uitkomst (``nan``) te
    vertrouwen.
    """
    afstand__deg = np.asarray(afstand__deg, dtype=float)
    uitkomst = np.zeros_like(afstand__deg)
    niet_nul = afstand__deg > 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        uitkomst[niet_nul] = afstand__deg[niet_nul] ** 2 * np.log(afstand__deg[niet_nul])
    return uitkomst


def _euclidische_afstanden__deg(punten_a: np.ndarray, punten_b: np.ndarray) -> np.ndarray:
    """Afstandsmatrix tussen twee puntenwolken (elk ``(_, 2)``: ``[lat, lon]``)."""
    verschillen = punten_a[:, None, :] - punten_b[None, :, :]
    return np.sqrt(np.sum(verschillen ** 2, axis=-1))


def geo_gewichten(
    stations__deg: np.ndarray,
    doel_lat__degN: float,
    doel_lon__degE: float,
) -> np.ndarray:
    """Gewichten waarmee stationswaarden naar één doellocatie interpoleren.

    Thin-plate-spline RBF met een polynoomterm van graad 1: functioneel
    gelijk aan ``scipy.interpolate.RBFInterpolator(stations, y, kernel=
    "thin_plate_spline", degree=1, smoothing=0)`` voor elke ``y``, zie de
    moduledocstring voor de afleiding.

    Parameters
    ----------
    stations__deg   : ``(n, 2)`` array, per station ``[lat__degN, lon__degE]``.
    doel_lat__degN,
    doel_lon__degE  : de doellocatie, in decimale graden.

    Returns
    -------
    ``(n,)`` array ``w``, in dezelfde volgorde als ``stations__deg``, zodat
    ``interpoleer(waarden, w)`` de geïnterpoleerde reeks geeft.

    De gewichten sommeren tot 1 (de graad-1-polynoom reproduceert een
    constante exact, zie ``tests/test_geo.py``), maar mogen individueel
    negatief zijn: een spline is geen gewogen gemiddelde.
    """
    stations__deg = np.asarray(stations__deg, dtype=float)
    if stations__deg.ndim != 2 or stations__deg.shape[1] != 2:
        raise ValueError(
            f"stations__deg moet vorm (n, 2) hebben ([lat__degN, lon__degE] per "
            f"station), kreeg vorm {stations__deg.shape}")
    n_stations = stations__deg.shape[0]
    if n_stations < _MIN_STATIONS:
        raise ValueError(
            f"geo_gewichten heeft minstens {_MIN_STATIONS} stations nodig voor "
            f"de polynoomterm van graad 1, kreeg er {n_stations}")

    kernelmatrix = _tps_kernel__0(_euclidische_afstanden__deg(stations__deg, stations__deg))
    polynoombasis = np.column_stack([np.ones(n_stations), stations__deg])  # kolommen: 1, lat, lon

    stelsel = np.block([
        [kernelmatrix, polynoombasis],
        [polynoombasis.T, np.zeros((3, 3))],
    ])

    doelpunt = np.array([[float(doel_lat__degN), float(doel_lon__degE)]])
    kernel_naar_doel = _tps_kernel__0(_euclidische_afstanden__deg(stations__deg, doelpunt)).ravel()
    rechterlid_doel = np.concatenate([kernel_naar_doel, [1.0, doelpunt[0, 0], doelpunt[0, 1]]])

    # De coëfficiënten (a, b) zijn lineair in de metingen y (het stelsel zelf
    # hangt niet van y af), dus ook de waarde op de doellocatie is dat. Die
    # lineaire afbeelding y -> waarde(doel) is de rij van inverse(stelsel) die
    # bij rechterlid_doel hoort; we lezen hem af via solve met de
    # getransponeerde matrix in plaats van een expliciete inverse (stabieler,
    # en het stelsel is symmetrisch op het nulblok na, dus dit kost niets).
    oplossing = np.linalg.solve(stelsel.T, rechterlid_doel)
    return oplossing[:n_stations]


def interpoleer(waarden: np.ndarray, gewichten: np.ndarray) -> np.ndarray:
    """Pas vaste gewichten toe op een tijdreeks van stationswaarden.

    Parameters
    ----------
    waarden   : ``(t, n)`` array: per tijdstip de waarde van elk station, in
                dezelfde stationsvolgorde als waarmee ``gewichten`` is bepaald.
    gewichten : ``(n,)`` array uit :func:`geo_gewichten`.

    Returns
    -------
    ``(t,)`` array met de geïnterpoleerde reeks op de doellocatie.

    Dit is de volledige interpolatiestap voor een heel jaar: één
    matrixvermenigvuldiging, geen lus over tijdstippen. ``NaN`` bij een
    station werkt door naar elk tijdstip waar dat station ontbreekt: dat is
    opzet, een stil doorgerekend gat zou het gat juist onzichtbaar maken.
    """
    gewichten = np.asarray(gewichten, dtype=float)
    waarden = np.asarray(waarden, dtype=float)
    if waarden.ndim != 2 or waarden.shape[1] != gewichten.shape[0]:
        raise ValueError(
            f"waarden moet vorm (t, {gewichten.shape[0]}) hebben (t tijdstippen, "
            f"evenveel stations als gewichten), kreeg vorm {waarden.shape}")
    return waarden @ gewichten
