# SPDX-License-Identifier: EUPL-1.2
"""
behoeften.py: het behoefteplan: hoe de kern zegt wat hij nodig heeft.

Dit is het API-aspect dat in de echte kern van Kenniscentrum Duurzaam Leven nog helemaal
ontbreekt (ontwerpdocument §5). ``behoeften(invoer)`` is een **pure functie**
van de parameters, geen I/O, geen netwerk, geen state: zodat een schil hem
mag aanroepen zodra de gebruiker de eerste parameters heeft ingevuld, ver
vóórdat er iets te simuleren valt (prefetch, §5.2).

Twee soorten behoeften, met elk hun eigen dataclass:

* ``PakketBehoefte`` : een open datapakket dat wij zelf maken (het weer- en
  het prijspakket in ``pakketten/``). Draagt een naam, een minimumversie en
  een dekking; de kern kent geen URL's (§5.2). Beide pakketten zijn
  **landelijk**: het weerpakket uit privacyoverwegingen (alle KNMI-
  meetpunten, geen reeks per locatie), het prijspakket omdat een prijs nu
  eenmaal geen locatie heeft. De kern interpoleert het weerpakket zelf naar
  zijn eigen locatie (zie ``kern.geo``); de dekking van de pakketbehoefte
  zelf draagt daarom geen ``lat``/``lon`` meer.
* ``Behoefte``       : een grootheid, nooit een kanaal (§5.3). Draagt vier
  velden: ``grootheid__str``, ``noodzaak__cat``, ``terugval__str`` en
  ``gewicht__0``. De eigen locatie van de afnemer (``locatie_lat_lon``) is
  hiervan een voorbeeld: dat is precies de grootheid die een adresregister-/
  BAG-ingestkanaal kan voeden, en precies de parameter die ``kern.geo``
  betekenisvol maakt.

De kern zelf gebruikt dit plan alleen om vóór de run te bepalen of hij kan
rekenen (zie ``kern.model``): ontbreekt een **verplichte** behoefte, dan
rekent hij niet en meldt hij dat netjes terug (§5.6) in plaats van een
exception te gooien.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .parameters import SimulatieParameters

Noodzaak = Literal["verplicht", "verbetert"]


@dataclass(frozen=True)
class Dekking:
    """Dekking van een pakketbehoefte (§5.2): jaar, interval, en of hij landelijk is.

    Geen ``lat__degN``/``lon__degE`` meer: beide pakketten die de kern nodig
    heeft (weer, prijzen) zijn **landelijk** (§5.2, ``kern.geo``), niet
    locatiespecifiek. Voor het weerpakket is dat een privacykeuze van de
    uitgever: zou er al een reeks per locatie klaarstaan, dan zou het
    opvragen van dat pakket zelf al een locatiemelding zijn. De eigen locatie
    van de afnemer hoort dus nooit in de dekking van een pakketbehoefte; die
    staat apart, als de ``locatie_lat_lon``-behoefte hieronder.
    """
    kalenderjaar: int
    interval_min: int
    landelijk__bool: bool = True


@dataclass(frozen=True)
class PakketBehoefte:
    """Een open-datapakketbehoefte: naam, minimumversie en dekking, geen URL."""
    naam__str: str
    minimumversie: int
    dekking: Dekking


@dataclass(frozen=True)
class Behoefte:
    """Eén behoefte aan een grootheid (nooit een kanaal), met terugval en gewicht.

    Attributen
    ----------
    grootheid__str : wélke grootheid, in physiquant__unit-naamgeving.
    noodzaak__cat  : "verplicht" of "verbetert".
    terugval__str  : wat het model gebruikt als de grootheid ontbreekt.
    gewicht__0     : grove indicatie (0-1) van hoeveel de grootheid uitmaakt
                     voor de uitkomst.
    """
    grootheid__str: str
    noodzaak__cat: Noodzaak
    terugval__str: str
    gewicht__0: float


@dataclass(frozen=True)
class BehoeftePlan:
    """Het volledige behoefteplan van één simulatie: pakketten + grootheden."""
    pakketbehoeften: tuple[PakketBehoefte, ...]
    behoeften: tuple[Behoefte, ...]

    def verplichte_pakketbehoeften(self) -> tuple[PakketBehoefte, ...]:
        return self.pakketbehoeften

    def verplichte_behoeften(self) -> tuple[Behoefte, ...]:
        return tuple(b for b in self.behoeften if b.noodzaak__cat == "verplicht")


#: Naam en minimumversie van het weerpakket: het enige verplichte pakket
#: (§5.7): zonder weer kan de kern niet rekenen en is er geen zinnige terugval.
#: Landelijk: alle KNMI-meetpunten, geen reeks per locatie (zie ``kern.geo``
#: voor de interpolatiestap die daar de consequentie van is).
WEERPAKKET_NAAM = "weer/synthetisch-uur"
WEERPAKKET_MINVERSIE = 3

#: Het prijspakket is alleen verplicht als de batterij op een prijssignaal stuurt.
PRIJSPAKKET_NAAM = "prijzen/synthetisch-placeholder"
PRIJSPAKKET_MINVERSIE = 1


def behoeften(invoer: SimulatieParameters) -> BehoeftePlan:
    """Pure functie: geef het behoefteplan voor deze parameters.

    Geen I/O: dit inspecteert alleen ``invoer`` en retourneert data. Zie de
    moduledocstring en het ontwerpdocument §5 voor de achterliggende regels.
    """
    dekking = Dekking(kalenderjaar=invoer.kalenderjaar, interval_min=invoer.interval_min)

    pakketbehoeften: list[PakketBehoefte] = [
        PakketBehoefte(naam__str=WEERPAKKET_NAAM, minimumversie=WEERPAKKET_MINVERSIE, dekking=dekking),
    ]
    if invoer.batterij_toevoegen__bool and invoer.batterij.stuurregel__cat == "prijssignaal":
        pakketbehoeften.append(
            PakketBehoefte(naam__str=PRIJSPAKKET_NAAM, minimumversie=PRIJSPAKKET_MINVERSIE, dekking=dekking))

    persoonlijke_behoeften: list[Behoefte] = [
        # Eigen behoefte, los van dakoriëntatie: deze lat/lon voedt niet alleen
        # de zonpositie in de PV-laag, maar is sinds kern.geo ook de doellocatie
        # van de weerinterpolatie. Precies dát maakt lat/lon een grootheid die
        # een adresregister-/BAG-ingestkanaal zinvol kan voeden (§5.3: een
        # behoefte noemt een grootheid, nooit het kanaal zelf).
        Behoefte(
            grootheid__str="locatie_lat_lon",
            noodzaak__cat="verbetert",
            terugval__str="landelijk gemiddelde locatie (midden van Nederland), "
                          "zie STANDAARD_LAT__DEGN/STANDAARD_LON__DEGE",
            gewicht__0=0.7,
        ),
        Behoefte(
            grootheid__str="dakoriëntatie",
            noodzaak__cat="verbetert",
            terugval__str="zuid-georiënteerd dak, 35° helling",
            gewicht__0=0.4,
        ),
        Behoefte(
            grootheid__str="basislast__W",
            noodzaak__cat="verbetert",
            terugval__str="synthetisch verbruiksprofiel, geschaald naar het opgegeven jaarverbruik",
            gewicht__0=0.5,
        ),
    ]
    if invoer.pv_toevoegen__bool:
        persoonlijke_behoeften.append(
            Behoefte(
                grootheid__str="pv_opbrengst_gemeten__kWh",
                noodzaak__cat="verbetert",
                terugval__str="geen kalibratie: de berekende opbrengst wordt ongewijzigd gebruikt",
                gewicht__0=0.3,
            )
        )
    if invoer.batterij_toevoegen__bool:
        persoonlijke_behoeften.append(
            Behoefte(
                grootheid__str="batterij_capaciteit_en_vermogen",
                noodzaak__cat="verplicht",
                terugval__str="geen, zonder deze waarden kan de batterijlaag niet rekenen",
                gewicht__0=1.0,
            )
        )

    return BehoeftePlan(pakketbehoeften=tuple(pakketbehoeften), behoeften=tuple(persoonlijke_behoeften))
