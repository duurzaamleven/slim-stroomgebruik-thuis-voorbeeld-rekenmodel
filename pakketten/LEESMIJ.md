# LEESMIJ: dit is een testfixture, geen bruikbaar weerpakket

⚠️ **Lees dit voordat je iets met deze bestanden doet.**

## Wat hier staat

Drie kleine CSV-bestanden:

- `weer_synthetisch_testfixture_2023.csv`: **landelijk**, meerstations. Lang formaat, één rij per
  station per tijdstip: `station_id, tijdstip, temperatuur__degC, instraling__W_m_2,
  windsnelheid__m_s`. 6 meetpunten × 336 tijdstippen (twee weken, 1 t/m 14 maart 2023, uurbasis) =
  2016 rijen.
- `weer_synthetisch_testfixture_stations_2023.csv`: de bijbehorende stationsmetadata,
  `station_id, naam, lat__degN, lon__degE`, verspreid over een NL-achtige rechthoek.
- `prijzen_synthetisch_testfixture_placeholder_2023.csv`: een synthetische dag/nacht-prijsreeks,
  336 rijen, óók landelijk (een prijs heeft geen locatie).

Plus `manifest.json`, dat alle bestanden beschrijft op precies dezelfde manier als een echt
datapakket dat zou doen (naam, versie, sha256, dekking, licentie-achtige velden): zodat de schil
(`schil/cli.py`) en het behoefteplan-mechanisme (`kern/behoeften.py`) er ongewijzigd tegenaan
kunnen matchen.

## Waarom het weerpakket landelijk is, en niet één reeks

Zou hier één reeks per opgegeven locatie klaarstaan, dan zou het **opvragen** van dat pakket zelf al
een locatiemelding zijn: de uitgever zou dan altijd weten waar een afnemer woont. Daarom is het
weerpakket landelijk (alle meetpunten tegelijk), en interpoleert de **afnemer** zelf naar zijn eigen
`lat__degN`/`lon__degE`, op zijn eigen apparaat. Zie `kern/geo.py` voor die interpolatiestap en
`kern/behoeften.py` voor hoe het behoefteplan dit als een aparte, eigen behoefte van de locatie
zelf onderscheidt (los van het pakket).

## Wat dit nadrukkelijk NIET is

1. **Geen jaardata.** Het beslaat twee weken, niet een heel kalenderjaar. Vraag je de CLI om een
   ander deel van het jaar dan 1-14 maart, dan krijg je buiten dat venster een **plat
   doorgetrokken** waarde (de laatste/eerste bekende meting), niet een zinnige jaarreeks.
2. **Geen realistisch stationsnet.** 6 synthetische meetpunten, niet de 22 van het echte landelijke
   pakket, en op willekeurig gekozen coördinaten (geen echte KNMI-locaties): net genoeg om
   `kern/geo.py` offline te kunnen toetsen (minstens 3 nodig voor de polynoomterm van graad 1, dit
   testfixture geeft er ruim boven het minimum), niet om als weerbeeld te dienen.
3. **Geen realistische pieken, met opzet.** De waarden per station zijn:

   | grootheid | in dit testfixture | echte Nederlandse extremen (KNMI, zie hieronder) |
   |---|---|---|
   | globale straling | piekt op 432-480 W/m² (per station iets gedempt) | 900-1000 W/m² |
   | temperatuur | ruwweg 1 tot 11 °C (per station een klein, vast verschil) | ruwweg -10 tot +35 °C |
   | windsnelheid | per station constant, 3,1-4,0 m/s | tot boven de 15 m/s |

   Elk station volgt dezelfde gladde dagcyclus (geen bewolking, geen dag-tot-dag-variatie, geen
   seizoensgang) met daar bovenop een klein, vast en verzonnen ruimtelijk verschil. Dat is bewust:
   een quasi-realistisch jaarpakket in deze repo zou uitnodigen tot gebruik, en een eerste indruk
   op te gladde data geeft precies de verkeerde intuïtie voor een opdracht die over **pieken** gaat,
   niet over jaarsommen.
4. **Geen echte marktprijzen.** De prijsreeks is een simpel, verzonnen dag/nacht-tarief (dal
   € 0,15/kWh 's nachts en in het weekend, piek € 0,28/kWh doordeweeks overdag), geen ENTSO-E,
   geen ACM-tarievenbesluit.

## Waar het wél realistisch is

**`slim-stroomgebruik-thuis-datapakketten`** (aparte repo, nog niet openbaar). Daar staan:

- `weer/knmi-uur-debilt-2023`: echte KNMI-uurdata voor één meetpunt, heel 2023;
- `weer/knmi-uur-nl-2023`: echte KNMI-uurdata, **landelijk**, alle 22 meetpunten, heel 2023: dit
  is het echte pakket waarvoor `kern/geo.py` is geschreven;
- `prijzen/placeholder-uur-2023`: dezelfde soort synthetische placeholder als hier, maar dan voor
  een heel jaar, met een uitgebreidere herkomstregistratie.

Wil je een uitkomst die iets zegt over een echte woning of een echt jaar, gebruik dan die repo,
niet dit testfixture.

## Waarom dit hier toch als bestand staat, en niet als losse in-memory fixture

De kern-tests (`tests/`) genereren hun eigen weerdata (meerstations, in het geheugen, zie
`tests/conftest.py`) en zijn dus niet van deze bestanden afhankelijk. Dit CSV-testfixture bestaat
voor de **schil** (`schil/cli.py`): die matcht tegen `manifest.json` en leest bestanden van schijf,
en dat pad moet ook zonder netwerktoegang blijven werken: vandaar kleine, gecommitte bestanden in
plaats van een download.
