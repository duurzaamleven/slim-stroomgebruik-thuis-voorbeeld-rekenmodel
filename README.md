# voorbeeldrekenmodel

> ⚠️ **Dit model is NIET geschikt om uitspraken over een echte woning mee te
> doen.** Alle brondata in deze repo is synthetisch en verzonnen (zie
> `pakketten/`), de fysica is expres vereenvoudigd, en er zit geen enkele
> validatie tegen een echte meting in. Gebruik dit niet als adviesinstrument,
> citeer het niet als rekenresultaat, en behandel elke uitkomst als een
> demonstratie van de **interface**, niet van de **inhoud**.

> ⚠️ **`pakketten/` is een testfixture, geen datapakket.** Het bevat twee
> weken verzonnen data, met opzet zonder realistische pieken, alleen om de
> tests en de CLI van deze repo offline te kunnen draaien. Het echte,
> herverspreidbare weerpakket (echte KNMI-meetdata, `CC-BY-4.0`) staat in de
> aparte repo **`slim-stroomgebruik-thuis-datapakketten`** (nog niet openbaar). Hoe je
> daarmee een heel jaar rekent: zie *Rekenen met een heel jaar echt weer* hieronder.

## Wat dit is

Een klein, volledig door Kenniscentrum Duurzaam Leven geschreven rekenmodel dat drie
domeinlagen simuleert: een zomertijd-correcte tijd-as, een PV-opbrengstketen
en een thuisbatterij, en dat elk aspect van de API bevat die het *echte*
simulatiemodel van Kenniscentrum Duurzaam Leven ook heeft: één stabiele aanroep
(`simuleer(invoer) -> uitvoer`), een expliciet in- en uitvoerdatamodel,
geïnjecteerde brondata (de kern doet zelf geen acquisitie), een cache-
protocol, semantische voortgangsevents, een expliciet behoefteplan, een
contractversie, en een annuleringspunt.

Het bestaat zodat studenten die een eigen rekenmodel achter een generieke API
bouwen tegen **iets van realistisch rekengewicht**
kunnen ontwikkelen zonder de echte, niet-publiceerbare rekenkern van Kenniscentrum Duurzaam
Leven in te hoeven zien of te distribueren.

**Wat het nadrukkelijk niet is:** geen warmtebalans, geen schilmodel, geen
NTA 8800, geen woningcatalogus, geen bruikbaar advies. De motivatie van deze keuzes staat in een
intern ontwerpdocument van Kenniscentrum Duurzaam Leven; als de code of deze README naar
"het ontwerpdocument" met een paragraafnummer verwijst, is dat document bedoeld.

## Hoe je het draait

Vereist Python 3.11+.

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt
pytest
python -m schil.cli --jaar 2024 --interval 60
```

Staat er geen kopie van de datapakketten op je computer (zie hieronder), dan rekent de CLI met het
testfixture en zegt hij dat met een `[WAARSCHUWING]`. De tests die het echte weerpakket nodig hebben,
worden dan overgeslagen.

Nuttige CLI-opties (zie `python -m schil.cli --help`): `--datapakketten PAD`, `--interval 15|60`,
`--panelen`, `--pv-azimut`, `--pv-helling`, `--geen-pv`, `--geen-batterij`,
`--stuurregel eigen_verbruik|prijssignaal`, `--jaarverbruik`.

## Indeling

```
voorbeeldrekenmodel/
├── kern/            de rekenkern: simuleer(invoer) -> uitvoer, en verder niets
├── pakketten/       MINIMAAL TESTFIXTURE (twee weken, geen realistische pieken) + manifest
├── schil/           één referentieschil (CLI) die de kern van buitenaf aanstuurt
├── distributie/     allowlist + test die de afhankelijkheden van kern/ bewaakt
└── tests/           pytest
```

De kern importeert uitsluitend `numpy`, `pandas` en de standaardbibliotheek
(inclusief `zoneinfo`), geen `scipy`, geen netwerk, geen bestands-I/O. Zie
`distributie/allowlist.py` en de bijbehorende test.

Het weerpakket dat de kern binnenkrijgt is **landelijk** (alle meetpunten
tegelijk, geen reeks per locatie: een privacykeuze van de uitgever). De kern
interpoleert dat pakket zelf naar zijn eigen `lat__degN`/`lon__degE`, met
alleen `numpy` (`kern/geo.py`: thin-plate-spline RBF-interpolatie, exact
gelijk aan `scipy.interpolate.RBFInterpolator` in zijn standaardinstelling,
maar zonder de `scipy`-afhankelijkheid). `scipy` staat wél in
`requirements-dev.txt`: uitsluitend om die gelijkheid in `tests/test_geo.py`
te toetsen, nooit als kernafhankelijkheid.

## Rekenen met een heel jaar echt weer

Deze repo bevat zelf geen bruikbare weer- of prijsdata. `pakketten/` is een
**minimaal testfixture**: twee weken verzonnen data over 6 synthetische
meetpunten (landelijk, net als het echte pakket, maar dan minimaal), kort
genoeg om niemand op het idee te brengen er iets mee te berekenen, en met
opzet zonder realistische pieken (zie `pakketten/LEESMIJ.md`). Het bestaat
uitsluitend om `pytest` en `python -m schil.cli` offline te laten werken.

Het echte weer staat in de aparte repo **`slim-stroomgebruik-thuis-datapakketten`**
(nog niet openbaar; toegang via Kenniscentrum Duurzaam Leven): per kalenderjaar
een landelijk pakket met de KNMI-uurwaarnemingen van alle 22 meetpunten,
`weer/knmi-nl-2023`, `weer/knmi-nl-2024` en `weer/knmi-nl-2025`, elk met een
`HERKOMST.md`. Die scheiding volgt uit het ontwerpdocument (§5.2 en §6): data en
code zijn verschillende werken met verschillende licenties, en een jaarpakket in
déze coderepo zou uitnodigen tot gebruik waar het niet voor bedoeld is.

**Ophalen.** Zet een kopie van die repo naast deze:

```bash
cd ..
git clone git@github.com:duurzaamleven/slim-stroomgebruik-thuis-datapakketten.git
cd slim-stroomgebruik-thuis-voorbeeld-rekenmodel
python -m schil.cli --jaar 2024
```

Staat de kopie ergens anders, geef dan `--datapakketten PAD` mee of zet de
omgevingsvariabele `DATAPAKKETTEN_MAP`. De CLI zoekt in het `manifest.json`
van die repo het pakket dat het behoefteplan vraagt, controleert de `sha256`
en leest de parquet.

**Hoe de kern het pakket kiest.** Het behoefteplan (`kern/behoeften.py`) vraagt
het weerpakket van het gevraagde kalenderjaar: `--jaar 2024` geeft
`weer/knmi-nl-2024`. Weer is een meting op een echte datum, dus er is geen
terugval op een ander jaar. Vindt de CLI het pakket niet, dan valt hij terug op
het testfixture, met een waarschuwing; de kern meldt zelf ook als het weer de
tijd-as niet helemaal dekt.

**Een eigen schil (bijvoorbeeld in de browser).** Lees de parquet zelf in en
geef hem aan `kern.weerpakket.knmi_weerpakket_naar_kern`; die zet het pakket om
naar de `weerdata` en `weerstations` die `simuleer` verwacht:

```python
import pandas as pd
from kern.model import simuleer
from kern.parameters import SimulatieParameters
from kern.weerpakket import knmi_weerpakket_naar_kern

weerdata, weerstations = knmi_weerpakket_naar_kern(
    pd.read_parquet("weer/knmi-nl-2024/knmi_nl_2024_60min.parquet"))
uitvoer = simuleer(SimulatieParameters(kalenderjaar=2024),
                   weerdata=weerdata, weerstations=weerstations)
```

De omzetting verandert alleen namen en vorm (`buitentemperatuur__degC` wordt
`temperatuur__degC`, `globale_straling__W_m_2` wordt `instraling__W_m_2`,
`windsnelheid__m_s_1` wordt `windsnelheid__m_s`; de eenheden zijn gelijk). Bij
enkele meetpunten ontbreken in 2024 en 2025 uren of dagen; de kern interpoleert
dan per tijdstip uit de meetpunten die er wél zijn.

Zoals de datapakketten-repo zelf zegt: **GitHub is de overdracht, niet de
runtime.** Een webapplicatie haalt het pakket niet tijdens het gebruik bij
GitHub op, maar zet het naast zichzelf op de eigen server.

**Licentie en naamsvermelding.** De KNMI-waarnemingen staan onder `CC-BY-4.0`
van het KNMI. Wie ze gebruikt of laat zien, vermeldt de bron; de precieze tekst
staat in het veld `attributie` van het manifest (de CLI drukt hem af). Het prijspakket
blijft voorlopig het testfixture van twee weken; voor de stuurregel
`prijssignaal` over een heel jaar is er nog geen geschikt pakket.

## Licentie

De code valt onder de European Union Public Licence 1.2 (`EUPL-1.2`). Zie [`LICENSE`](LICENSE)
voor de volledige tekst.

Copyright © 2026 Kenniscentrum Duurzaam Leven, Stichting Milieu Centraal.

`EUPL-1.2` staat via de compatibiliteitsclausule (artikel 5) toe dat dit model wordt opgenomen in
een geheel dat onder `AGPL-3.0` wordt verspreid, zoals bij WattDeFlex.

Dit model is bedoeld als ontwikkelhulpmiddel, niet als onderdeel van een product. Dat is een
bedoeling, geen licentievoorwaarde.

## Geen pull requests

Dit project accepteert **geen bijdragen van derden** (geen pull requests).

De reden is eenvoudig: dit is **gereedschap**, geschreven om tegenaan te ontwikkelen, en het hoort
van een hand te zijn. Daar komt bij dat Kenniscentrum Duurzaam Leven het volledige auteursrecht houdt
zolang zij alle code zelf schrijft, en dat houdt de mogelijkheid open de licentie later te wijzigen
of aan te vullen. Zodra een externe bijdrage wordt opgenomen, geldt dat niet meer voor dat deel van
de code.

Wil je iets voorstellen: open een issue, geen pull request. Een enthousiaste bijdrage mag niet voor
niets zijn.

## Credits

Zie `CREDITS.md` voor de literatuurverwijzingen achter de PV-keten
(Michalsky 1988, Erbs e.a. 1982, Hay & Davies 1980, Spencer 1971) en de
positie van pvlib daarin (validatiereferentie, geen bron).
