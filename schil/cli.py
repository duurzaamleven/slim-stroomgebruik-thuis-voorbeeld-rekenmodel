# SPDX-License-Identifier: EUPL-1.2
"""
cli.py: de referentieschil van het voorbeeldrekenmodel.

Dit is de **enige** schil in deze repo (ontwerpdocument §9): één command-line
programma dat aantoont dat de kern schil-onafhankelijk is. Alles wat hier
staat, hoort bij de schil en NIET bij de kern:

  * bestanden lezen (de datapakketten uit ``pakketten/``, tegen het manifest);
  * een cache-implementatie (``BestandsCache``, hier een simpel bestand op
    schijf: het "bestand nu, IndexedDB straks" uit §4);
  * voortgang naar stdout schrijven;
  * Ctrl-C afvangen en vertalen naar het annuleringspunt van de kern.

De kern zelf (``kern.model.simuleer``) kent niets van bestanden, paden of
stdout: hij krijgt kant-en-klare ``pandas``-structuren en een ``Melder``-
callback aangereikt. Vervang deze schil door een browser-worker en de kern
verandert niet.

Gebruik
-------
    python -m schil.cli --jaar 2023 --interval 60
"""
from __future__ import annotations

import argparse
import json
import pickle
import signal
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Console-onafhankelijk: op Windows staat stdout soms op een codepage die geen
# pijltjes/graden-tekens kent (bv. cp1252). We forceren UTF-8 zodat de CLI
# overal hetzelfde gedrag heeft: dit is puur schilzijdig, de kern raakt hier
# niets van.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

from kern.behoeften import behoeften
from kern.model import simuleer
from kern.parameters import BatterijParameters, PVVeld, SimulatieParameters
from kern.uitvoer import CONTRACT_VERSIE
from kern.voortgang import Voortgang

PAKKETTEN_DIR = Path(__file__).resolve().parent.parent / "pakketten"
CACHE_BESTAND = Path(__file__).resolve().parent.parent / ".cache_schil.pkl"


# ── Cache-implementatie: een simpel bestand op schijf ────────────────────────
# Voldoet structureel aan kern.cache.Cache (geen erving nodig: Protocol).
# Dit is precies het "bestand nu, IndexedDB straks"-punt uit het ontwerp: een
# browserschil vervangt deze klasse door iets dat IndexedDB gebruikt, zonder
# dat de kern iets hoeft te weten. Pickle i.p.v. JSON, want de kern cachet
# hier o.a. een pandas ``DatetimeIndex``, geen JSON-primitief. Dit bestand is
# puur lokaal en zelfgegenereerd (geen externe/onvertrouwde invoer), dus
# pickle is hier veilig; een gedeelde of publieke cache zou een ander formaat
# vragen.
class BestandsCache:
    """Cache-implementatie die de kern.cache.Cache-protocol volgt (structureel)."""

    def __init__(self, pad: Path) -> None:
        self._pad = pad
        self._data: dict[str, Any] = {}
        if pad.exists():
            try:
                self._data = pickle.loads(pad.read_bytes())
            except (pickle.PickleError, OSError, EOFError):
                self._data = {}

    def haal_op(self, sleutel: str) -> Any | None:
        return self._data.get(sleutel)

    def zet(self, sleutel: str, waarde: Any) -> None:
        self._data[sleutel] = waarde
        self._pad.write_bytes(pickle.dumps(self._data))

    def bevat(self, sleutel: str) -> bool:
        return sleutel in self._data


# ── Pakketten inlezen + tegen het manifest matchen (§5.2) ────────────────────

def _laad_manifest() -> dict:
    return json.loads((PAKKETTEN_DIR / "manifest.json").read_text(encoding="utf-8"))


def _match_pakket(manifest: dict, naam: str, minimumversie: int) -> dict:
    """Zoek het pakket met deze naam in het manifest en controleer de versie.

    De kern noemt alleen een naam en een minimumversie (§5.2); dit matchen
    en het uiteindelijk ophalen is schilwerk.
    """
    for pakket in manifest["pakketten"]:
        if pakket["naam"] == naam:
            if pakket["versie"] < minimumversie:
                raise RuntimeError(
                    f"pakket {naam!r} gevonden maar versie {pakket['versie']} "
                    f"< vereiste minimumversie {minimumversie}")
            return pakket
    raise RuntimeError(f"pakket {naam!r} niet gevonden in manifest")


def _lees_tijdreeks_csv(pad: Path, waarde_kolommen: list[str]) -> pd.DataFrame:
    df = pd.read_csv(pad, parse_dates=["tijdstip"])
    df["tijdstip"] = pd.to_datetime(df["tijdstip"], utc=True)
    df = df.set_index("tijdstip")
    return df[waarde_kolommen]


def _lees_landelijk_weerpakket(pakket: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lees het landelijke (meerstations) weerpakket + zijn stationsmetadata.

    Retourneert ``(weerdata, weerstations)`` precies in de vorm die
    ``kern.model.simuleer`` verwacht: ``weerdata`` met een 2-level kolom-
    ``MultiIndex`` (grootheid, station_id), ``weerstations`` geïndexeerd op
    ``station_id`` met de kolommen ``lat__degN``/``lon__degE``. Het lange
    CSV-formaat (één rij per station per tijdstip) wordt hier gepivoteerd
    naar dat brede formaat: dat pivotteren is schilwerk, de kern zelf leest
    nooit een CSV.
    """
    metingen_pad = PAKKETTEN_DIR / pakket["bestand"]
    stations_pad = PAKKETTEN_DIR / pakket["stations_bestand"]

    metingen = pd.read_csv(metingen_pad, parse_dates=["tijdstip"])
    metingen["tijdstip"] = pd.to_datetime(metingen["tijdstip"], utc=True)
    weerdata = metingen.pivot_table(
        index="tijdstip", columns="station_id",
        values=["temperatuur__degC", "instraling__W_m_2", "windsnelheid__m_s"],
    )

    weerstations = pd.read_csv(stations_pad).set_index("station_id")
    return weerdata, weerstations


# ── Voortgang naar stdout ────────────────────────────────────────────────────

def _print_voortgang(v: Voortgang) -> None:
    prefix = "[WAARSCHUWING]" if v.ernst == "waarschuwing" else "[info]"
    aandeel = f" ({v.aandeel__0:.0%})" if v.aandeel__0 is not None else ""
    print(f"{prefix} {v.fase}: {v.boodschap}{aandeel}")


# ── Annulering via Ctrl-C ─────────────────────────────────────────────────────

class _AnnuleerVlag:
    """Simpele vlag die op ``True`` gaat bij SIGINT (Ctrl-C).

    Dit is de schilzijdige helft van het annuleringspunt (§4.1): de kern kent
    geen signalen, hij pollt alleen een callable. De schil vertaalt "gebruiker
    drukt op Ctrl-C" naar dat callable.
    """

    def __init__(self) -> None:
        self.gezet = False

    def __call__(self) -> bool:
        return self.gezet

    def handler(self, signum, frame) -> None:
        if not self.gezet:
            print("\n[info] annulering aangevraagd (Ctrl-C): stopt bij de volgende pollmoment...")
        self.gezet = True


def _bouw_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Referentieschil van het voorbeeldrekenmodel (Kenniscentrum Duurzaam Leven; EUPL-1.2). "
                    "NIET geschikt om uitspraken over een echte woning mee te doen.")
    p.add_argument("--jaar", type=int, default=2023, help="kalenderjaar (standaard 2023)")
    p.add_argument("--interval", type=int, default=60, choices=(15, 60),
                    help="intervallengte in minuten: 15 of 60 (standaard 60)")
    p.add_argument("--lat", type=float, default=52.1326, help="breedtegraad")
    p.add_argument("--lon", type=float, default=5.2913, help="lengtegraad")
    p.add_argument("--panelen", type=int, default=12, help="aantal PV-panelen")
    p.add_argument("--pv-azimut", type=float, default=180.0,
                    help="paneelazimut in graden (0=noord, met de klok mee, zuid=180)")
    p.add_argument("--pv-helling", type=float, default=35.0, help="hellingshoek in graden")
    p.add_argument("--geen-pv", action="store_true", help="PV-laag uitschakelen")
    p.add_argument("--geen-batterij", action="store_true", help="batterijlaag uitschakelen")
    p.add_argument("--stuurregel", choices=("eigen_verbruik", "prijssignaal"), default="eigen_verbruik")
    p.add_argument("--jaarverbruik", type=float, default=3000.0, help="basislast-jaarverbruik in kWh")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _bouw_argparser().parse_args(argv)

    print(f"voorbeeldrekenmodel: referentie-CLI (contract_versie {CONTRACT_VERSIE})")
    print("LET OP: dit model is NIET geschikt om uitspraken over een echte woning mee te doen.\n")
    print(f"locatie: lat {args.lat:.4f}, lon {args.lon:.4f} "
          f"(doellocatie van de PV-zonpositie én van de weerinterpolatie, zie kern/geo.py)\n")

    invoer = SimulatieParameters(
        kalenderjaar=args.jaar,
        interval_min=args.interval,
        locatie_lat__degN=args.lat,
        locatie_lon__degE=args.lon,
        pv_toevoegen__bool=not args.geen_pv,
        pv_velden=(PVVeld(aantal_panelen__0=args.panelen, azimut__deg=args.pv_azimut,
                           hellingshoek__deg=args.pv_helling),),
        batterij_toevoegen__bool=not args.geen_batterij,
        batterij=BatterijParameters(stuurregel__cat=args.stuurregel),
        basislast_jaarverbruik__kWh=args.jaarverbruik,
    )

    # ── Stap 1: behoefteplan: pure functie, kan al vóór elke data-inlezing ──
    plan = behoeften(invoer)
    print("Behoefteplan (pure functie van de parameters, zie kern/behoeften.py):")
    for pb in plan.pakketbehoeften:
        print(f"  pakket   : {pb.naam__str} (min. versie {pb.minimumversie}, "
              f"jaar {pb.dekking.kalenderjaar})")
    for b in plan.behoeften:
        print(f"  grootheid: {b.grootheid__str} [{b.noodzaak__cat}, gewicht {b.gewicht__0}] "
              f"terugval: {b.terugval__str}")
    print()

    # ── Stap 2: pakketten inlezen tegen het manifest (schilwerk, geen kern) ──
    manifest = _laad_manifest()
    weer_df = None
    weerstations_df = None
    prijzen_df = None
    for pb in plan.pakketbehoeften:
        pakket = _match_pakket(manifest, pb.naam__str, pb.minimumversie)
        pad = PAKKETTEN_DIR / pakket["bestand"]
        print(f"  → pakket '{pb.naam__str}' gematcht op {pad.name} (versie {pakket['versie']})")
        if pakket.get("landelijk"):
            print(f"    landelijk pakket: {pakket.get('aantal_stations', '?')} stations, "
                  "afnemer interpoleert zelf naar zijn locatie (zie kern/geo.py)")
        if pakket.get("testfixture"):
            print("    [WAARSCHUWING] dit is een minimaal TESTFIXTURE (twee weken, met opzet "
                  "geen realistische pieken), geen bruikbare weer-/prijsdata. Zie "
                  "pakketten/LEESMIJ.md en de repo slim-stroomgebruik-thuis-datapakketten voor het "
                  "echte, herverspreidbare pakket.")
        if pb.naam__str.startswith("weer/"):
            weer_df, weerstations_df = _lees_landelijk_weerpakket(pakket)
            print(f"    stations gebruikt: {', '.join(sorted(weerstations_df.index))}")
        elif pb.naam__str.startswith("prijzen/"):
            prijzen_df = _lees_tijdreeks_csv(pad, ["prijs__EUR_kWh"])
    print()

    cache = BestandsCache(CACHE_BESTAND)

    vlag = _AnnuleerVlag()
    oude_handler = signal.signal(signal.SIGINT, vlag.handler)
    try:
        uitvoer = simuleer(
            invoer,
            weerdata=weer_df,
            weerstations=weerstations_df,
            prijsdata__EUR_kWh=(prijzen_df["prijs__EUR_kWh"] if prijzen_df is not None else None),
            cache=cache,
            meld=_print_voortgang,
            annuleer=vlag,
        )
    finally:
        signal.signal(signal.SIGINT, oude_handler)

    print()
    print(f"status: {uitvoer.status__cat}")
    if uitvoer.status__cat == "onvolledig":
        print(f"ontbrekende verplichte behoeften: {', '.join(uitvoer.ontbrekende_behoeften)}")
        return 1

    print(f"kalenderjaar: {uitvoer.kalenderjaar}, interval_min: {uitvoer.interval_min}, "
          f"aantal_intervallen: {uitvoer.aantal_intervallen}")
    print(f"locatie: lat {uitvoer.metadata.get('locatie_lat__degN'):.4f}, "
          f"lon {uitvoer.metadata.get('locatie_lon__degE'):.4f} "
          f"(weer geïnterpoleerd uit {uitvoer.metadata.get('weerstations_aantal', '?')} stations)")
    if "pv_ac__W" in uitvoer.intervallen:
        jaartotaal_pv__kWh = uitvoer.intervallen["pv_ac__W"].sum() * uitvoer.interval_min / 60000.0
        print(f"PV-jaaropbrengst: {jaartotaal_pv__kWh:.0f} kWh")
    if "batterij_laad__W" in uitvoer.intervallen:
        laad__kWh = uitvoer.intervallen["batterij_laad__W"].sum() * uitvoer.interval_min / 60000.0
        ontlaad__kWh = uitvoer.intervallen["batterij_ontlaad__W"].sum() * uitvoer.interval_min / 60000.0
        print(f"batterij: {laad__kWh:.0f} kWh geladen, {ontlaad__kWh:.0f} kWh ontladen")
    print()
    print("samenvatting (eerste kolommen):")
    print(uitvoer.samenvatting.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
