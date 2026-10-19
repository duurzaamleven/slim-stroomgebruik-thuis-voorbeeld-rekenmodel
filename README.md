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
> aparte repo **`slim-stroomgebruik-thuis-datapakketten`** (nog niet openbaar). Zie
> `pakketten/LEESMIJ.md` voor het volledige verhaal.

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
python -m schil.cli --jaar 2023 --interval 60
```

Nuttige CLI-opties (zie `python -m schil.cli --help`): `--interval 15|60`,
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

## Waar de échte datapakketten staan

Deze repo bevat zelf geen bruikbare weer- of prijsdata. `pakketten/` is een
**minimaal testfixture**: twee weken verzonnen data over 6 synthetische
meetpunten (landelijk, net als het echte pakket, maar dan minimaal), kort
genoeg om niemand op het idee te brengen er iets mee te berekenen, en met
opzet zonder realistische pieken (zie `pakketten/LEESMIJ.md` voor de exacte
waarden en de vergelijking met echte KNMI-extremen). Het bestaat uitsluitend
om `pytest` en `python -m schil.cli` offline en zonder netwerktoegang te
laten werken.

De echte, herverspreidbare datapakketten, inclusief een heel jaar echte
KNMI-uurdata voor De Bilt en voor heel Nederland: staan in de aparte repo
**`slim-stroomgebruik-thuis-datapakketten`** (nog niet openbaar), elk met een eigen `HERKOMST.md` en
licentieveld. Die scheiding volgt uit het ontwerpdocument (§5.2): data en code
zijn verschillende werken met verschillende licenties en levenscycli, en een
quasi-realistisch jaarpakket in déze coderepo zou bovendien uitnodigen tot
gebruik voor iets waar het niet geschikt voor is. De CLI hier gebruikt het
testfixture met een expliciete `[WAARSCHUWING]` in de uitvoer zodra dat
gebeurt: er is geen verborgen aanname dat de data realistisch is.

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
