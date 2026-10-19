# SPDX-License-Identifier: EUPL-1.2
"""
pv.py: gevectoriseerde PV-opbrengstketen: zonpositie → POA → DC → AC.

Zelfstandige implementatie (zie ``CREDITS.md`` en het ontwerpdocument §3.2/§6:
niets hiervan is overgenomen uit een andere repo van Kenniscentrum Duurzaam Leven). De keten
volgt vier onafhankelijk gepubliceerde, publieke astronomische/fysische
methoden:

  1. **Zonpositie** : Michalsky, J.J. (1988), "The Astronomical Almanac's
     algorithm for approximate solar position (1950-2050)", Solar Energy
     40(3), 227-235. Ecliptische-lengte-benadering + hemelsferische
     transformatie naar hoogte/azimut.
  2. **Extraterrestrische straling**: Spencer, J.W. (1971), "Fourier series
     representation of the position of the sun", Search 2(5), 172.
     Gebruikt hier voor de excentriciteitscorrectiefactor ``E0``.
  3. **Diffuus-splitsing**: Erbs, D.G., Klein, S.A. & Duffie, J.A. (1982),
     "Estimation of the diffuse radiation fraction for hourly, daily and
     monthly-average global radiation", Solar Energy 28(4), 293-302.
  4. **Transpositie naar het paneelvlak (POA)**: Hay, J.E. & Davies, J.A.
     (1980), "Calculation of the solar radiation incident on an inclined
     surface", Proc. First Canadian Solar Radiation Data Workshop.

``pvlib`` (BSD-3-Clause) is **geen** afhankelijkheid en geen bron van deze
code; het dient elders uitsluitend als offline validatiereferentie (zie
CREDITS.md). Deze module importeert alleen ``numpy`` en ``pandas``.

Eenheden volgen de ``physiquant__unit``-conventie. Azimut: 0° = noord, met de
klok mee, zuid = 180° (voor zowel de zon als een paneelveld).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .parameters import PVVeld

#: Zonneconstante (gemiddelde extraterrestrische bestraling loodrecht op de
#: zonnestralen, op gemiddelde zon-aarde-afstand).
GSC__W_M_2 = 1367.0

#: Vaste grondalbedo (aandeel gereflecteerd zonlicht); een toy-model hoeft dit
#: niet per locatie te variëren.
ALBEDO__0 = 0.20

#: Ondergrens van de zonshoogte waaronder we de zon als "onder de horizon"
#: behandelen (voorkomt numerieke ruis rond zonsopgang/-ondergang).
_MIN_ELEVATIE__DEG = 0.0


@dataclass(frozen=True)
class ZonPositie:
    """Zonshoogte en -azimut per interval, plus de excentriciteitsfactor."""
    elevatie__deg: np.ndarray
    azimut__deg: np.ndarray
    e0__0: np.ndarray  # Spencer-excentriciteitscorrectie (aarde-zon-afstand)


def _dagen_sinds_j2000(index: pd.DatetimeIndex) -> np.ndarray:
    """Continue dagteller sinds 1 januari 2000, 12:00 UTC (J2000.0-epoch)."""
    if index.tz is None:
        raise ValueError("pv.zonpositie verwacht een tijdzone-bewuste DatetimeIndex")
    utc = index.tz_convert("UTC")
    epoch = pd.Timestamp("2000-01-01T12:00:00", tz="UTC")
    delta = utc - epoch
    return delta.total_seconds().to_numpy() / 86400.0


def zonpositie(index: pd.DatetimeIndex, lat__degN: float, lon__degE: float) -> ZonPositie:
    """Bereken zonshoogte en -azimut volgens Michalsky (1988), gevectoriseerd.

    Parameters
    ----------
    index      : tz-bewuste ``DatetimeIndex`` (elke tijdzone; wordt intern naar
                 UTC omgezet).
    lat__degN  : breedtegraad, positief noorderbreedte.
    lon__degE  : lengtegraad, positief oosterlengte.
    """
    n = _dagen_sinds_j2000(index)

    # Middelbare baanelementen (Michalsky 1988, eq. 3-4).
    L__deg = np.mod(280.460 + 0.9856474 * n, 360.0)
    g__deg = np.mod(357.528 + 0.9856003 * n, 360.0)
    g__rad = np.radians(g__deg)

    # Ecliptische lengte en scheefstand (eq. 5-6).
    lam__deg = L__deg + 1.915 * np.sin(g__rad) + 0.020 * np.sin(2 * g__rad)
    lam__rad = np.radians(lam__deg)
    eps__deg = 23.439 - 0.0000004 * n
    eps__rad = np.radians(eps__deg)

    # Rechte klimming en declinatie (eq. 7-9).
    rechte_klimming__rad = np.arctan2(np.cos(eps__rad) * np.sin(lam__rad), np.cos(lam__rad))
    rechte_klimming__deg = np.mod(np.degrees(rechte_klimming__rad), 360.0)
    declinatie__rad = np.arcsin(np.sin(eps__rad) * np.sin(lam__rad))

    # Greenwich-sterrentijd (standaard IAU-benadering) → lokale sterrentijd → uurhoek.
    gmst__deg = np.mod(280.46061837 + 360.98564736629 * n, 360.0)
    lst__deg = np.mod(gmst__deg + lon__degE, 360.0)
    uurhoek__deg = np.mod(lst__deg - rechte_klimming__deg + 180.0, 360.0) - 180.0
    uurhoek__rad = np.radians(uurhoek__deg)

    lat__rad = np.radians(lat__degN)

    # Hoogte (Meeus, sferische astronomie: standaardformule, publiek domein).
    sin_el = (np.sin(lat__rad) * np.sin(declinatie__rad)
              + np.cos(lat__rad) * np.cos(declinatie__rad) * np.cos(uurhoek__rad))
    elevatie__rad = np.arcsin(np.clip(sin_el, -1.0, 1.0))

    # Azimut vanaf het zuiden, positief westwaarts (Meeus eq. 13.5), omgezet naar
    # onze conventie (0 = noord, met de klok mee): +180°.
    teller = np.sin(uurhoek__rad)
    noemer = (np.cos(uurhoek__rad) * np.sin(lat__rad)
              - np.tan(declinatie__rad) * np.cos(lat__rad))
    azimut_zuid__deg = np.degrees(np.arctan2(teller, noemer))
    azimut__deg = np.mod(azimut_zuid__deg + 180.0, 360.0)

    # Spencer (1971): excentriciteitscorrectiefactor van de aarde-zonafstand.
    doy = index.tz_convert("UTC").dayofyear.to_numpy().astype(float)
    gamma__rad = 2 * np.pi * (doy - 1) / 365.0
    e0__0 = (1.000110 + 0.034221 * np.cos(gamma__rad) + 0.001280 * np.sin(gamma__rad)
             + 0.000719 * np.cos(2 * gamma__rad) + 0.000077 * np.sin(2 * gamma__rad))

    return ZonPositie(elevatie__deg=np.degrees(elevatie__rad), azimut__deg=azimut__deg, e0__0=e0__0)


def splits_diffuus_erbs(globale_straling__W_m_2: np.ndarray, zon: ZonPositie) -> tuple[np.ndarray, np.ndarray]:
    """Splits globale straling (GHI) in direct-normaal (DNI) en diffuus-horizontaal
    (DHI) volgens de Erbs-correlatie (Erbs, Klein & Duffie 1982).

    Returns
    -------
    (direct_normaal__W_m_2, diffuus_horizontaal__W_m_2)
    """
    ghi = np.asarray(globale_straling__W_m_2, dtype=float)
    elevatie__rad = np.radians(zon.elevatie__deg)
    cos_zenit = np.clip(np.sin(elevatie__rad), 0.0, 1.0)  # cos(zenit) = sin(elevatie)

    g0__W_m_2 = GSC__W_M_2 * zon.e0__0 * cos_zenit  # extraterrestrische straling, horizontaal
    with np.errstate(divide="ignore", invalid="ignore"):
        kt__0 = np.where(g0__W_m_2 > 1.0, ghi / g0__W_m_2, 0.0)
    kt__0 = np.clip(kt__0, 0.0, 1.0)

    kd__0 = np.select(
        [kt__0 <= 0.22, kt__0 <= 0.80],
        [1.0 - 0.09 * kt__0,
         0.9511 - 0.1604 * kt__0 + 4.388 * kt__0 ** 2 - 16.638 * kt__0 ** 3 + 12.336 * kt__0 ** 4],
        default=0.165,
    )
    kd__0 = np.clip(kd__0, 0.0, 1.0)

    diffuus_horizontaal__W_m_2 = kd__0 * ghi
    with np.errstate(divide="ignore", invalid="ignore"):
        direct_normaal__W_m_2 = np.where(cos_zenit > 0.01, (ghi - diffuus_horizontaal__W_m_2) / cos_zenit, 0.0)
    direct_normaal__W_m_2 = np.clip(direct_normaal__W_m_2, 0.0, None)

    # Boven de horizon dwingen we alles naar nul, geen straling zonder zon.
    boven_horizon = zon.elevatie__deg > _MIN_ELEVATIE__DEG
    direct_normaal__W_m_2 = np.where(boven_horizon, direct_normaal__W_m_2, 0.0)
    diffuus_horizontaal__W_m_2 = np.where(boven_horizon, diffuus_horizontaal__W_m_2, 0.0)
    return direct_normaal__W_m_2, diffuus_horizontaal__W_m_2


def poa_hay_davies(globale_straling__W_m_2: np.ndarray, direct_normaal__W_m_2: np.ndarray, diffuus_horizontaal__W_m_2: np.ndarray,
                    zon: ZonPositie, azimut_paneel__deg: float, helling__deg: float) -> np.ndarray:
    """Instraling in het paneelvlak (POA) volgens het anisotrope model van
    Hay & Davies (1980): directe component + anisotrope hemelcomponent
    (circumsolair + isotroop) + grondreflectie.
    """
    el__rad = np.radians(zon.elevatie__deg)
    az_verschil__rad = np.radians(zon.azimut__deg - azimut_paneel__deg)
    helling__rad = np.radians(helling__deg)

    cos_aoi = (np.sin(el__rad) * np.cos(helling__rad)
               + np.cos(el__rad) * np.sin(helling__rad) * np.cos(az_verschil__rad))
    cos_aoi = np.clip(cos_aoi, 0.0, None)
    cos_zenit = np.clip(np.sin(el__rad), 0.0, 1.0)

    poa_direct__W_m_2 = direct_normaal__W_m_2 * cos_aoi

    g0_normaal__W_m_2 = GSC__W_M_2 * zon.e0__0  # extraterrestrisch, loodrecht op de stralen
    with np.errstate(divide="ignore", invalid="ignore"):
        ai__0 = np.where(g0_normaal__W_m_2 > 1.0, direct_normaal__W_m_2 / g0_normaal__W_m_2, 0.0)
    ai__0 = np.clip(ai__0, 0.0, 1.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        rb__0 = np.where(cos_zenit > 0.01, cos_aoi / cos_zenit, 0.0)
    rb__0 = np.clip(rb__0, 0.0, 5.0)  # begrensd tegen singulariteit rond de horizon

    poa_hemel__W_m_2 = diffuus_horizontaal__W_m_2 * (ai__0 * rb__0 + (1 - ai__0) * (1 + np.cos(helling__rad)) / 2)
    poa_grond__W_m_2 = globale_straling__W_m_2 * ALBEDO__0 * (1 - np.cos(helling__rad)) / 2

    poa__W_m_2 = poa_direct__W_m_2 + poa_hemel__W_m_2 + poa_grond__W_m_2
    boven_horizon = zon.elevatie__deg > _MIN_ELEVATIE__DEG
    return np.where(boven_horizon, np.clip(poa__W_m_2, 0.0, None), 0.0)


# ── DC → systeemverlies → omvormer-clipping → AC ─────────────────────────────

#: Temperatuurcoëfficiënt van het vermogen (typisch voor kristallijn silicium).
GAMMA_VERMOGEN__W0_DEGC_1 = -0.004

#: Nominal Operating Cell Temperature: eenvoudig celtemperatuurmodel.
NOCT__DEGC = 45.0


def celtemperatuur__degC(temp_lucht__degC: np.ndarray, poa__W_m_2: np.ndarray) -> np.ndarray:
    """Eenvoudig NOCT-celtemperatuurmodel (Duffie & Beckman-achtig, standaardvorm)."""
    return np.asarray(temp_lucht__degC, dtype=float) + (NOCT__DEGC - 20.0) / 800.0 * poa__W_m_2


def pv_ac_vermogen__W(
    index: pd.DatetimeIndex,
    globale_straling__W_m_2: np.ndarray,
    temp_lucht__degC: np.ndarray,
    lat__degN: float,
    lon__degE: float,
    velden: tuple[PVVeld, ...],
    vermogen_per_paneel__Wp: float,
    omvormer_capaciteit__W: float,
    eta_omvormer__W0: float,
    systeemverlies__0: float,
) -> pd.Series:
    """Volledige keten: zonpositie → POA per veld → DC → systeemverlies →
    omvormer-clipping → AC. Geeft het AC-vermogen in W terug, als Series op
    ``index``.
    """
    zon = zonpositie(index, lat__degN, lon__degE)
    direct_normaal__W_m_2, diffuus_horizontaal__W_m_2 = splits_diffuus_erbs(globale_straling__W_m_2, zon)

    pdc_totaal__W = np.zeros(len(index), dtype=float)
    for veld in velden:
        poa__W_m_2 = poa_hay_davies(globale_straling__W_m_2, direct_normaal__W_m_2, diffuus_horizontaal__W_m_2, zon,
                                     veld.azimut__deg, veld.hellingshoek__deg)
        celtemp__degC = celtemperatuur__degC(temp_lucht__degC, poa__W_m_2)
        pdc_per_paneel__W = (vermogen_per_paneel__Wp * (poa__W_m_2 / 1000.0)
                              * (1 + GAMMA_VERMOGEN__W0_DEGC_1 * (celtemp__degC - 25.0)))
        pdc_per_paneel__W = np.clip(pdc_per_paneel__W, 0.0, None)
        pdc_totaal__W += pdc_per_paneel__W * veld.aantal_panelen__0

    pdc_na_verlies__W = pdc_totaal__W * (1.0 - systeemverlies__0)
    pac_voor_clip__W = pdc_na_verlies__W * eta_omvormer__W0
    pac__W = np.clip(np.minimum(pac_voor_clip__W, omvormer_capaciteit__W), 0.0, None)
    return pd.Series(pac__W, index=index, name="pv_ac__W")
