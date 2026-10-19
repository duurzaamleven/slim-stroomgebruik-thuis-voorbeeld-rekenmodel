# Credits

De PV-keten in `kern/pv.py` is een **zelfstandige implementatie**, niet
afgeleid van pvlib of enige andere bibliotheek of repository. De volgende vier
publicaties beschrijven de methoden die zijn geïmplementeerd:

- **Zonpositie**: Michalsky, J.J. (1988), *"The Astronomical Almanac's
  algorithm for approximate solar position (1950–2050)"*, Solar Energy 40(3),
  227–235.
- **Extraterrestrische straling** (excentriciteitscorrectie): Spencer, J.W.
  (1971), *"Fourier series representation of the position of the sun"*,
  Search 2(5), 172.
- **Diffuus-splitsing** (GHI → DNI + DHI): Erbs, D.G., Klein, S.A. & Duffie,
  J.A. (1982), *"Estimation of the diffuse radiation fraction for hourly,
  daily and monthly-average global radiation"*, Solar Energy 28(4), 293–302.
- **Transpositie naar het paneelvlak (POA)**: Hay, J.E. & Davies, J.A.
  (1980), *"Calculation of the solar radiation incident on an inclined
  surface"*, Proceedings of the First Canadian Solar Radiation Data Workshop.

## pvlib: validatiereferentie, geen bron

[pvlib-python](https://github.com/pvlib/pvlib-python) (`BSD-3-Clause`) wordt
hier genoemd als **onafhankelijke validatiereferentie**: het implementeert
dezelfde vier publieke methoden, en een onafhankelijke tweede implementatie
van dezelfde publicaties is de gebruikelijke manier om er vertrouwen in te
krijgen dat een eigen implementatie de literatuur correct volgt.

**Onze PV-keten is niet van pvlib afgeleid, is er geen fork of vendoring van,
en pvlib is geen afhankelijkheid van dit project.** Er is geen regel code uit
pvlib overgenomen. Dit is dus geen licentiekwestie (pvlib's BSD-3-Clause zou
sowieso nergens een probleem geven), maar een feitelijke: de
implementatie hier is zelfstandig geschreven op basis van de publicaties
hierboven.

## kern/geo.py: dezelfde functie als scipy, niet dezelfde code

`kern/geo.py` lost, met alleen `numpy`, hetzelfde wiskundige probleem op als
`scipy.interpolate.RBFInterpolator` in zijn standaardinstelling
(thin-plate-spline-kernel, polynoomterm van graad 1, `smoothing=0`): een
zadelpuntstelsel dat rechtstreeks met `numpy.linalg.solve` wordt opgelost.
Geen regel is uit scipy's broncode overgenomen; de afleiding staat in de
moduledocstring van `kern/geo.py`.

`scipy` (`BSD-3-Clause`) wordt hier, net als pvlib hierboven, uitsluitend als
**validatiereferentie** gebruikt: `tests/test_geo.py` toetst dat beide
implementaties op hetzelfde probleem tot dezelfde uitkomst komen (verschil
< 1e-9), niet dat `kern/geo.py` van scipy afgeleid is. `scipy` is daarom een
**testafhankelijkheid** (`requirements-dev.txt`), nooit een afhankelijkheid
van `kern/` zelf: zie `distributie/allowlist.py` en de bijbehorende test, die
dat bewaken.

## Overige software

Dit project gebruikt zelf alleen [`numpy`](https://numpy.org/) en
[`pandas`](https://pandas.pydata.org/) (beide `BSD-3-Clause`), plus de
standaardbibliotheek van Python (inclusief `zoneinfo`, met op Windows het
pakket [`tzdata`](https://github.com/python/tzdata) (Python Software
Foundation License) voor de tijdzonedatabase). Zie `requirements.txt` en
`requirements-dev.txt` voor de volledige lijst inclusief testafhankelijkheden
(waaronder `scipy`, alleen gebruikt in `tests/test_geo.py`, zie hierboven).
