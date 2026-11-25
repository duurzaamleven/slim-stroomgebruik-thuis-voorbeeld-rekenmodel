# SPDX-License-Identifier: EUPL-1.2
"""
weerpakket.py: een KNMI-weerpakket omzetten naar de vorm die ``simuleer`` verwacht.

Waarom deze module bestaat
---------------------------
Het echte weerpakket (``weer/knmi-nl-JJJJ`` uit de repo
``slim-stroomgebruik-thuis-datapakketten``) en de kern spreken net een andere
taal:

* vorm: het pakket is lang (één rij per meetpunt per tijdstip), de kern
  wil breed (kolommen grootheid × station_id);
* tijd: in het pakket de kolom ``timestamp``, in de kern de index;
* meetpunt: in het pakket ``lat__degN``/``lon__degE`` op elke rij, in de kern
  een ``station_id`` plus een aparte stationstabel;
* namen: ``buitentemperatuur__degC`` heet in de kern ``temperatuur__degC``,
  ``globale_straling__W_m_2`` heet ``instraling__W_m_2`` en
  ``windsnelheid__m_s_1`` heet ``windsnelheid__m_s``.

De eenheden zijn gelijk (°C, W/m², m/s); alleen de namen verschillen. De
kernnamen zijn ouder dan het pakket, en ze veranderen zou het contract van
``simuleer`` breken voor iedereen die al weerdata aanlevert. Daarom staat de
vertaling hier, op één plek, als expliciete tabel (``KNMI_NAAR_KERN``).

Waarom in de kern en niet in de schil
--------------------------------------
Dit is een **pure functie**: een DataFrame erin, twee DataFrames eruit. Geen
bestand, geen netwerk, geen parquet-lezer: het inlezen blijft schilwerk. Maar
de vertaling zelf hoort bij het contract tussen pakket en kern, en elke schil
(de CLI hier, een browser-worker bij WattDeFlex) heeft hem nodig. Staat hij in
de kern, dan hoeft geen enkele schil hem na te bouwen.

Gaten in het pakket (een meetpunt dat een paar uur of dagen ontbreekt) worden
hier niet aangevuld: zo'n rij ontbreekt gewoon en wordt in de brede vorm een
``NaN``. ``kern.model`` interpoleert per tijdstip uit de meetpunten die er wél
zijn (``kern.geo.interpoleer_met_gaten``).
"""
from __future__ import annotations

import pandas as pd

#: Tijdkolom in het KNMI-pakket (tz-bewust, Europe/Amsterdam).
KNMI_TIJDKOLOM = "timestamp"

#: Coördinaatkolommen: in het pakket per rij, in de kern in de stationstabel.
LAT_KOLOM = "lat__degN"
LON_KOLOM = "lon__degE"

#: Grootheden die de kern gebruikt: naam in het KNMI-pakket -> naam in de kern.
#: Zelfde eenheid aan beide kanten; zie de moduledocstring.
KNMI_NAAR_KERN: dict[str, str] = {
    "buitentemperatuur__degC": "temperatuur__degC",
    "globale_straling__W_m_2": "instraling__W_m_2",
    "windsnelheid__m_s_1": "windsnelheid__m_s",
}


def _station_id(lat__degN: pd.Series, lon__degE: pd.Series) -> pd.Series:
    """Een leesbare, stabiele sleutel per meetpunt, afgeleid van de coördinaten.

    Het pakket heeft geen eigen stations-id; de coördinaten (drie decimalen,
    zoals het KNMI ze publiceert) zijn per meetpunt uniek.
    """
    return lat__degN.map("{:.3f}N".format) + "_" + lon__degE.map("{:.3f}E".format)


def knmi_weerpakket_naar_kern(metingen: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zet een KNMI-weerpakket (lang formaat) om naar ``(weerdata, weerstations)``.

    Parameters
    ----------
    metingen : het pakket zoals het uit de parquet komt: kolommen
               ``timestamp`` (tz-bewust), ``lat__degN``, ``lon__degE`` en
               minstens de grootheden in ``KNMI_NAAR_KERN``. Overige kolommen
               (luchtdruk, vochtigheid) worden genegeerd.

    Returns
    -------
    ``weerdata``    : kolom-``MultiIndex`` (grootheid in kernnaam, station_id),
                      index de tijdstippen, gesorteerd.
    ``weerstations``: index ``station_id``, kolommen ``lat__degN``/``lon__degE``.

    Precies de twee argumenten ``weerdata=`` en ``weerstations=`` van
    ``kern.model.simuleer``.
    """
    verplicht = {KNMI_TIJDKOLOM, LAT_KOLOM, LON_KOLOM, *KNMI_NAAR_KERN}
    ontbrekend = verplicht - set(metingen.columns)
    if ontbrekend:
        raise ValueError(
            f"dit lijkt geen KNMI-weerpakket: kolommen ontbreken: {sorted(ontbrekend)}")
    tijd = pd.DatetimeIndex(metingen[KNMI_TIJDKOLOM])
    if tijd.tz is None:
        raise ValueError(
            f"kolom {KNMI_TIJDKOLOM!r} moet tijdzonebewust zijn; zonder tijdzone is "
            "zomer- en wintertijd niet te onderscheiden")

    station_id = _station_id(metingen[LAT_KOLOM], metingen[LON_KOLOM])
    lang = metingen.assign(station_id=station_id.to_numpy(), tijdstip=tijd)

    weerstations = (lang.groupby("station_id")[[LAT_KOLOM, LON_KOLOM]].first()
                    .sort_index())

    # pivot (niet pivot_table): een dubbele rij voor hetzelfde meetpunt en
    # tijdstip is een fout in het pakket en moet een fout geven, geen gemiddelde.
    weerdata = lang.pivot(index="tijdstip", columns="station_id", values=list(KNMI_NAAR_KERN))
    weerdata = weerdata.rename(columns=KNMI_NAAR_KERN, level=0).sort_index().sort_index(axis=1)
    weerdata.columns = weerdata.columns.set_names(["grootheid", "station_id"])
    return weerdata, weerstations
