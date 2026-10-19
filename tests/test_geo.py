# SPDX-License-Identifier: EUPL-1.2
"""Toetsen van kern/geo.py: de numpy-only geospatiale interpolatie.

De belangrijkste toets hier is de gelijkheidstoets tegen
``scipy.interpolate.RBFInterpolator`` (§ moduledocstring van ``kern.geo``):
dit is geen benadering van scipy's gedrag maar dezelfde wiskundige functie,
en dat moet je kunnen aantonen, niet alleen beweren. ``scipy`` is hier een
**testafhankelijkheid** (``requirements-dev.txt``), geen kernafhankelijkheid:
zie ``distributie/allowlist.py`` en ``distributie/test_allowlist.py``, die
bewaken dat ``kern/`` zelf nooit scipy importeert.
"""
from __future__ import annotations

import numpy as np
import pytest

from kern.geo import geo_gewichten, interpoleer

# Een NL-achtige rechthoek: zes punten, ruim verspreid, met één punt dicht bij
# het landelijk gemiddelde midden (zie kern/parameters.py) zodat er ook een
# doellocatie in het "midden" van de puntenwolk getoetst kan worden.
_STATIONS__DEG = np.array([
    [53.00, 4.00],   # noordwest
    [53.20, 6.90],   # noordoost
    [51.20, 3.60],   # zuidwest
    [50.90, 5.90],   # zuidoost
    [52.10, 5.30],   # midden
    [52.30, 4.80],   # west
])

_DOELLOCATIES = [
    (52.1326, 5.2913),  # landelijk gemiddelde (STANDAARD_LAT__DEGN/LON__DEGE)
    (51.00, 4.00),       # buiten de puntenwolk, richting zuidwest
    (53.00, 7.00),       # buiten de puntenwolk, richting noordoost
    (52.50, 5.00),       # binnenin de puntenwolk
]


def test_gewichten_sommeren_tot_een():
    """De graad-1-polynoomterm reproduceert een constante exact, dus w.sum() == 1."""
    for lat, lon in _DOELLOCATIES:
        w = geo_gewichten(_STATIONS__DEG, lat, lon)
        assert w.sum() == pytest.approx(1.0, abs=1e-9)


def test_lineair_veld_komt_exact_terug():
    """Een lineair veld a + b*lat + c*lon moet, op elke doellocatie, exact
    worden gereproduceerd: dat is precies wat de graad-1-polynoomterm
    garandeert (thin-plate-spline-RBF met polynoomcorrectie is exact op de
    ruimte die de polynoomterm opspant)."""
    rng = np.random.default_rng(1)
    for _ in range(10):
        a, b, c = rng.normal(size=3)
        waarden = a + b * _STATIONS__DEG[:, 0] + c * _STATIONS__DEG[:, 1]
        for lat, lon in _DOELLOCATIES:
            w = geo_gewichten(_STATIONS__DEG, lat, lon)
            resultaat = interpoleer(waarden.reshape(1, -1), w)[0]
            verwacht = a + b * lat + c * lon
            assert resultaat == pytest.approx(verwacht, abs=1e-7)


def test_interpoleren_op_stationlocatie_geeft_die_meting():
    """Vraag je de doellocatie exact gelijk aan een station, dan moet de
    interpolant terugvallen op de meting van precies dat station."""
    rng = np.random.default_rng(2)
    for station_idx in range(len(_STATIONS__DEG)):
        lat, lon = _STATIONS__DEG[station_idx]
        w = geo_gewichten(_STATIONS__DEG, lat, lon)
        waarden = rng.normal(size=(3, len(_STATIONS__DEG)))
        resultaat = interpoleer(waarden, w)
        np.testing.assert_allclose(resultaat, waarden[:, station_idx], atol=1e-7)


def test_gewichten_hangen_niet_af_van_de_waarden():
    """geo_gewichten kent de metingen niet eens (ze zijn geen parameter): de
    lineariteit is dus al zichtbaar aan de signatuur. Wat wél getoetst hoort
    te worden is dat interpoleer() daadwerkelijk lineair is in de waarden
    (superpositie), want dát is de eigenschap waar de rest van de kern op
    leunt (kern/model.py past dezelfde gewichten toe op elke grootheid)."""
    rng = np.random.default_rng(3)
    w = geo_gewichten(_STATIONS__DEG, 52.0, 5.0)
    y1 = rng.normal(size=(4, len(_STATIONS__DEG)))
    y2 = rng.normal(size=(4, len(_STATIONS__DEG)))
    alpha, beta = 2.3, -0.7

    links = interpoleer(alpha * y1 + beta * y2, w)
    rechts = alpha * interpoleer(y1, w) + beta * interpoleer(y2, w)
    np.testing.assert_allclose(links, rechts, atol=1e-9)


def test_determinisme():
    """Gelijke invoer geeft bit-identieke uitvoer, geen toevalsgenerator."""
    w1 = geo_gewichten(_STATIONS__DEG, 52.3, 4.9)
    w2 = geo_gewichten(_STATIONS__DEG, 52.3, 4.9)
    np.testing.assert_array_equal(w1, w2)

    rng = np.random.default_rng(4)
    waarden = rng.normal(size=(20, len(_STATIONS__DEG)))
    r1 = interpoleer(waarden, w1)
    r2 = interpoleer(waarden, w2)
    np.testing.assert_array_equal(r1, r2)


def test_te_weinig_stations_geeft_duidelijke_fout():
    twee_stations = _STATIONS__DEG[:2]
    with pytest.raises(ValueError, match="minstens 3 stations"):
        geo_gewichten(twee_stations, 52.0, 5.0)


def test_verkeerde_vorm_stations_geeft_duidelijke_fout():
    plat = _STATIONS__DEG.ravel()  # (12,) i.p.v. (6, 2)
    with pytest.raises(ValueError, match="vorm"):
        geo_gewichten(plat, 52.0, 5.0)

    drie_kolommen = np.column_stack([_STATIONS__DEG, np.zeros(len(_STATIONS__DEG))])
    with pytest.raises(ValueError, match="vorm"):
        geo_gewichten(drie_kolommen, 52.0, 5.0)


def test_verkeerde_vorm_waarden_geeft_duidelijke_fout():
    w = geo_gewichten(_STATIONS__DEG, 52.0, 5.0)
    verkeerd_aantal_stations = np.zeros((10, len(_STATIONS__DEG) - 1))
    with pytest.raises(ValueError, match="vorm"):
        interpoleer(verkeerd_aantal_stations, w)

    eendimensionaal = np.zeros(len(_STATIONS__DEG))
    with pytest.raises(ValueError, match="vorm"):
        interpoleer(eendimensionaal, w)


def test_gelijk_aan_scipy_rbfinterpolator():
    """De kerntoets: verschil met scipy.interpolate.RBFInterpolator (dezelfde
    standaardinstelling: thin_plate_spline, degree=1, smoothing=0) moet onder
    1e-9 blijven, over veel willekeurige waardevectoren en doellocaties."""
    scipy_interpolate = pytest.importorskip("scipy.interpolate")

    rng = np.random.default_rng(12345)
    n_stations = len(_STATIONS__DEG)
    max_afwijking = 0.0

    for lat, lon in _DOELLOCATIES:
        gewichten = geo_gewichten(_STATIONS__DEG, lat, lon)
        doel__deg = np.array([[lat, lon]])
        for _ in range(50):
            waarden = rng.normal(loc=10.0, scale=5.0, size=n_stations)

            eigen_uitkomst = interpoleer(waarden.reshape(1, -1), gewichten)[0]

            rbf = scipy_interpolate.RBFInterpolator(
                _STATIONS__DEG, waarden,
                kernel="thin_plate_spline", degree=1, smoothing=0.0,
            )
            scipy_uitkomst = rbf(doel__deg)[0]

            max_afwijking = max(max_afwijking, abs(eigen_uitkomst - scipy_uitkomst))

    assert max_afwijking < 1e-9, f"afwijking t.o.v. scipy te groot: {max_afwijking:.3e}"
