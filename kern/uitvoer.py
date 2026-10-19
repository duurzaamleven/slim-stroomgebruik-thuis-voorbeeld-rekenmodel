# SPDX-License-Identifier: EUPL-1.2
"""
uitvoer.py: het uitvoerdatamodel van de rekenkern.

``SimulatieUitvoer`` is het spiegelbeeld van ``SimulatieParameters``: één
object terug in plaats van losse DataFrames, zodat een schil precies één ding
hoeft te kennen. Zie het ontwerpdocument §4 voor de motivatie per veld.

``CONTRACT_VERSIE`` is het gat dat het ontwerp expliciet benoemt (§4.1): zodra
een rekenmodel los van zijn schil wordt gedistribueerd, moet een schil kunnen
zien welke kernversie hij aanroept. Wat een schil daarmee doet (weigeren,
waarschuwen, een migratie proberen) is aan de schil.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

#: Semver van het simuleer(invoer) -> uitvoer-contract. Ophogen bij een
#: incompatibele wijziging van SimulatieParameters of SimulatieUitvoer.
#: 2.0.0: ``weerdata`` is nu een landelijk (meerstations) pakket en vereist
#: het nieuwe, verplichte gezelschapsargument ``weerstations`` (zie ``kern.geo``).
CONTRACT_VERSIE = "2.0.0"

#: Status van een simulatie-uitkomst. "voltooid" = normale uitkomst;
#: "onvolledig" = een verplichte behoefte ontbrak, er is niet gerekend (zie
#: kern/behoeften.py en §5.6 van het ontwerp); "geannuleerd" = de aanroeper
#: heeft de run via het annuleringspunt afgebroken (§4.1), met eventueel een
#: deelresultaat in ``intervallen``.
Status = Literal["voltooid", "onvolledig", "geannuleerd"]


@dataclass(frozen=True)
class SimulatieUitvoer:
    """
    Gestructureerde uitvoer van één jaarsimulatie.

    Attributen
    ----------
    contract_versie      : zie ``CONTRACT_VERSIE``.
    status__cat           : zie ``Status``.
    intervallen           : tijd-as + weer-/pv-/batterijkolommen. Leeg bij
                             status "onvolledig"; mogelijk een deelresultaat
                             bij "geannuleerd".
    samenvatting          : ``.describe()``-achtige jaartotalen/-kentallen,
                             met een kolom "statistiek".
    kalenderjaar          : het gesimuleerde jaar.
    interval_min          : intervalengte in minuten (15 of 60).
    aantal_intervallen    : lengte van de tijd-as (bij status "voltooid").
    kolommen              : kolomnamen van ``intervallen``.
    metadata              : platte, deterministische metadata (géén tijd-
                             stempels: dat zou de determinisme-eis breken),
                             bv. gebruikte pakketversies en locatie.
    ontbrekende_behoeften : namen van verplichte behoeften die ontbraken;
                             alleen gevuld bij status "onvolledig" (§5.6).
    """
    contract_versie: str
    status__cat: Status
    intervallen: pd.DataFrame
    samenvatting: pd.DataFrame
    kalenderjaar: int
    interval_min: int
    aantal_intervallen: int
    kolommen: list[str]
    metadata: dict = field(default_factory=dict)
    ontbrekende_behoeften: tuple[str, ...] = ()
