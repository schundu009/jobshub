#!/usr/bin/env python3
"""
Add life-sciences employers (pharma, biotech, genomics, health data, research
institutes) as job_boards rows.

These are the employers behind lifescience.net's listings. That site refuses
crawlers (robots.txt: Disallow / for every agent but search engines), so the
jobs come from each employer's own board instead. Only their computational
roles are kept (services.it_roles: bioinformatics, computational biology,
clinical data, LIMS, plus ordinary software / data / ML roles).

Each candidate names one or more guesses at its board; the first guess whose
public API lists jobs (services.ats_detect.probe) is kept. Workday guesses give
tenant/site and every common wdN host is tried. A board already scraped (by a
job_boards row or a coded scraper) or a slug already taken is skipped.

Usage (from backend/):
    python -m tools.add_life_sciences_boards            # dry run: what would be added
    python -m tools.add_life_sciences_boards --apply    # insert the rows
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from services import ats_detect  # noqa: E402

WORKDAY_HOSTS = ("wd1", "wd3", "wd5", "wd12", "wd103", "wd501")

# (company name, careers url, [(ats, board), ...]); workday boards are "tenant/site".
CANDIDATES: list[tuple[str, str, list[tuple[str, str]]]] = [
    # ------------------------------------------------ pharma
    ("Pfizer", "https://www.pfizer.com/about/careers", [("workday", "pfizer/PfizerCareers")]),
    ("Novartis", "https://www.novartis.com/careers", [("workday", "novartis/Novartis_Careers")]),
    ("Roche", "https://careers.roche.com", [("workday", "roche/roche-ext")]),
    ("AstraZeneca", "https://careers.astrazeneca.com", [("workday", "astrazeneca/Careers")]),
    ("GSK", "https://jobs.gsk.com", [("workday", "gsk/GSKCareers")]),
    ("Sanofi", "https://jobs.sanofi.com", [("workday", "sanofi/SanofiCareers")]),
    ("Johnson & Johnson", "https://www.careers.jnj.com", [("workday", "jj/JJ")]),
    ("Merck", "https://jobs.merck.com", [("workday", "msd/SearchJobs")]),
    ("Bristol Myers Squibb", "https://careers.bms.com", [("workday", "bristolmyerssquibb/BMS")]),
    ("Amgen", "https://careers.amgen.com", [("workday", "amgen/Careers")]),
    ("Gilead Sciences", "https://www.gilead.com/careers", [("workday", "gilead/gileadcareers")]),
    ("Regeneron", "https://careers.regeneron.com", [("workday", "regeneron/Careers")]),
    ("Vertex Pharmaceuticals", "https://www.vrtx.com/careers", [("workday", "vrtx/vertex_careers")]),
    ("Takeda", "https://jobs.takeda.com", [("workday", "takeda/External")]),
    ("Biogen", "https://www.biogen.com/careers", [("workday", "biibhr/external")]),
    ("Eli Lilly", "https://careers.lilly.com", [("workday", "lilly/LLY")]),
    ("Bayer", "https://career.bayer.com", [("workday", "bayer/Bayer_External")]),
    ("Moderna", "https://www.modernatx.com/careers", [("workday", "modernatx/M_tx")]),
    ("BioNTech", "https://jobs.biontech.com", [("workday", "biontech/BioNTech")]),
    ("Novo Nordisk", "https://www.novonordisk.com/careers", [("workday", "novonordisk/Novo_Nordisk")]),
    ("Boehringer Ingelheim", "https://www.boehringer-ingelheim.com/careers", [("workday", "boehringer/BI")]),
    ("Alnylam Pharmaceuticals", "https://www.alnylam.com/careers", [("workday", "alnylam/Alnylam")]),
    ("BeiGene", "https://www.beigene.com/careers", [("workday", "beigene/BeiGene")]),
    # ------------------------------------------------ tools, diagnostics, CROs
    ("Thermo Fisher Scientific", "https://jobs.thermofisher.com", [("workday", "thermofisher/ThermoFisherCareers")]),
    ("Illumina", "https://www.illumina.com/company/careers.html", [("workday", "illumina/illumina-careers")]),
    ("Danaher", "https://jobs.danaher.com", [("workday", "danaher/DanaherJobs")]),
    ("Agilent Technologies", "https://careers.agilent.com", [("workday", "agilent/Agilent_Careers")]),
    ("IQVIA", "https://jobs.iqvia.com", [("workday", "iqvia/IQVIA")]),
    ("Medtronic", "https://jobs.medtronic.com", [("workday", "medtronic/MedtronicCareers")]),
    ("Exact Sciences", "https://www.exactsciences.com/careers", [("workday", "exactsciences/Exact_Sciences")]),
    ("Guardant Health", "https://guardanthealth.com/careers", [("workday", "guardanthealth/Guardant_Health_Careers"),
                                                               ("greenhouse", "guardanthealth")]),
    ("Twist Bioscience", "https://www.twistbioscience.com/company/careers", [("greenhouse", "twistbioscience"),
                                                                             ("workday", "twistbioscience/Twist")]),
    ("Pacific Biosciences", "https://www.pacb.com/company/careers", [("workday", "pacb/PacBio")]),
    ("Bio-Rad Laboratories", "https://careers.bio-rad.com", [("workday", "biorad/BioRad_Careers")]),
    ("Revvity", "https://jobs.revvity.com", [("workday", "revvity/Revvity")]),
    ("Charles River Laboratories", "https://jobs.criver.com", [("workday", "criver/Careers")]),
    ("Labcorp", "https://careers.labcorp.com", [("workday", "labcorp/External")]),
    ("Certara", "https://www.certara.com/careers", [("workday", "certara/Certara"), ("greenhouse", "certara")]),
    # ------------------------------------------------ computational biotech, genomics, health data
    ("Recursion", "https://www.recursion.com/careers", [("greenhouse", "recursionpharmaceuticals"), ("lever", "recursion")]),
    ("insitro", "https://insitro.com/careers", [("greenhouse", "insitro"), ("lever", "insitro")]),
    ("Tempus", "https://www.tempus.com/careers", [("greenhouse", "tempus"), ("lever", "tempus")]),
    ("Benchling", "https://www.benchling.com/careers", [("greenhouse", "benchling"), ("ashby", "benchling")]),
    ("Ginkgo Bioworks", "https://www.ginkgobioworks.com/careers", [("greenhouse", "ginkgobioworks"), ("lever", "ginkgobioworks")]),
    ("Generate Biomedicines", "https://generatebiomedicines.com/careers", [("greenhouse", "generatebiomedicines"), ("lever", "generatebiomedicines")]),
    ("Isomorphic Labs", "https://www.isomorphiclabs.com/careers", [("greenhouse", "isomorphiclabs"), ("ashby", "isomorphiclabs")]),
    ("Xaira Therapeutics", "https://xaira.com/careers", [("greenhouse", "xairatherapeutics"), ("ashby", "xaira")]),
    ("Absci", "https://www.absci.com/careers", [("greenhouse", "absci"), ("lever", "absci")]),
    ("10x Genomics", "https://www.10xgenomics.com/careers", [("greenhouse", "10xgenomics")]),
    ("Freenome", "https://www.freenome.com/careers", [("greenhouse", "freenome"), ("lever", "freenome")]),
    ("GRAIL", "https://grail.com/careers", [("greenhouse", "grail"), ("workday", "grail/GRAIL")]),
    ("Natera", "https://www.natera.com/company/careers", [("greenhouse", "natera")]),
    ("23andMe", "https://www.23andme.com/careers", [("greenhouse", "23andme")]),
    ("Color Health", "https://www.color.com/careers", [("greenhouse", "color"), ("lever", "color")]),
    ("Flatiron Health", "https://flatiron.com/careers", [("greenhouse", "flatironhealth")]),
    ("Komodo Health", "https://www.komodohealth.com/careers", [("greenhouse", "komodohealth")]),
    ("Verily", "https://verily.com/careers", [("greenhouse", "verily"), ("workday", "verily/Verily")]),
    ("Owkin", "https://owkin.com/careers", [("lever", "owkin"), ("greenhouse", "owkin"), ("ashby", "owkin")]),
    ("Dyno Therapeutics", "https://www.dynotx.com/careers", [("greenhouse", "dynotherapeutics"), ("lever", "dynotx")]),
    ("Formation Bio", "https://formation.bio/careers", [("greenhouse", "formationbio"), ("ashby", "formationbio")]),
    ("Enveda", "https://www.envedabio.com/careers", [("greenhouse", "envedabiosciences"), ("lever", "enveda")]),
    ("Eikon Therapeutics", "https://eikontx.com/careers", [("greenhouse", "eikontherapeutics"), ("lever", "eikontx")]),
    ("Asimov", "https://www.asimov.com/careers", [("greenhouse", "asimov"), ("lever", "asimov"), ("ashby", "asimov")]),
    ("EvolutionaryScale", "https://www.evolutionaryscale.ai/careers", [("greenhouse", "evolutionaryscale"), ("ashby", "evolutionaryscale")]),
    ("Cradle", "https://www.cradle.bio/careers", [("ashby", "cradlebio"), ("ashby", "cradle")]),
    ("Altos Labs", "https://altoslabs.com/careers", [("greenhouse", "altoslabs")]),
    ("Calico", "https://www.calicolabs.com/careers", [("greenhouse", "calicolabs"), ("lever", "calicolabs")]),
    ("Arc Institute", "https://arcinstitute.org/careers", [("greenhouse", "arcinstitute"), ("ashby", "arcinstitute")]),
    ("Chan Zuckerberg Biohub", "https://www.czbiohub.org/careers", [("greenhouse", "czbiohub"), ("greenhouse", "biohub")]),
    ("Chan Zuckerberg Initiative", "https://chanzuckerberg.com/careers", [("greenhouse", "chanzuckerberginitiative")]),
    ("Schrödinger", "https://www.schrodinger.com/careers", [("greenhouse", "schrodinger"), ("lever", "schrodinger")]),
    ("Veeva Systems", "https://careers.veeva.com", [("lever", "veeva")]),
    ("Dotmatics", "https://www.dotmatics.com/careers", [("greenhouse", "dotmatics"), ("lever", "dotmatics")]),
    ("Sana Biotechnology", "https://sana.com/careers", [("greenhouse", "sanabiotechnology"), ("lever", "sana")]),
    ("Deep Genomics", "https://www.deepgenomics.com/careers", [("lever", "deepgenomics"), ("greenhouse", "deepgenomics")]),
    ("BigHat Biosciences", "https://www.bighatbio.com/careers", [("lever", "bighatbio"), ("greenhouse", "bighatbiosciences")]),
    ("Synthego", "https://www.synthego.com/careers", [("lever", "synthego"), ("greenhouse", "synthego")]),
    ("Inscripta", "https://www.inscripta.com/careers", [("lever", "inscripta"), ("greenhouse", "inscripta")]),
    ("Caris Life Sciences", "https://www.carislifesciences.com/careers", [("greenhouse", "carislifesciences"), ("workday", "caris/Caris")]),
    ("Invitae", "https://www.invitae.com/careers", [("greenhouse", "invitae"), ("lever", "invitae")]),
    ("Seer", "https://seer.bio/careers", [("greenhouse", "seer"), ("lever", "seer")]),
    ("Quantum-Si", "https://www.quantum-si.com/careers", [("greenhouse", "quantumsi"), ("lever", "quantum-si")]),
    ("Element Biosciences", "https://www.elementbiosciences.com/careers", [("greenhouse", "elementbiosciences"), ("lever", "elementbiosciences")]),
    ("Ultima Genomics", "https://www.ultimagenomics.com/careers", [("greenhouse", "ultimagenomics"), ("lever", "ultimagenomics")]),
    ("Tessera Therapeutics", "https://www.tesseratherapeutics.com/careers", [("greenhouse", "tesseratherapeutics"), ("lever", "tessera")]),
    ("Valo Health", "https://www.valohealth.com/careers", [("greenhouse", "valohealth"), ("lever", "valohealth")]),
    ("Iambic Therapeutics", "https://www.iambic.ai/careers", [("greenhouse", "iambictherapeutics"), ("ashby", "iambic")]),
    ("Genesis Therapeutics", "https://genesistherapeutics.ai/careers", [("greenhouse", "genesistherapeutics"), ("lever", "genesistherapeutics")]),
    ("Atomwise", "https://www.atomwise.com/careers", [("lever", "atomwise"), ("greenhouse", "atomwise")]),
    ("Exscientia", "https://www.exscientia.ai/careers", [("lever", "exscientia"), ("greenhouse", "exscientia")]),
    ("BenevolentAI", "https://www.benevolent.com/careers", [("lever", "benevolent"), ("greenhouse", "benevolentai")]),
    ("Relay Therapeutics", "https://relaytx.com/careers", [("greenhouse", "relaytherapeutics"), ("lever", "relaytx")]),
    ("Zymeworks", "https://www.zymeworks.com/careers", [("greenhouse", "zymeworks"), ("lever", "zymeworks")]),
    ("AbCellera", "https://www.abcellera.com/careers", [("greenhouse", "abcellera"), ("lever", "abcellera")]),
    ("Bioptimus", "https://www.bioptimus.com/careers", [("ashby", "bioptimus"), ("lever", "bioptimus")]),
    ("PathAI", "https://www.pathai.com/careers", [("greenhouse", "pathai"), ("lever", "pathai")]),
    ("Paige", "https://paige.ai/careers", [("greenhouse", "paige"), ("lever", "paige")]),
    ("Lunit", "https://www.lunit.io/careers", [("greenhouse", "lunit"), ("lever", "lunit")]),
    # ------------------------------------------------ research institutes
    ("Broad Institute", "https://www.broadinstitute.org/careers", [("workday", "broadinstitute/broad_institute"),
                                                                  ("workday", "broadinstitute/Broad_Institute_Careers")]),
    ("Allen Institute", "https://alleninstitute.org/careers", [("workday", "alleninstitute/Allen_Institute"),
                                                              ("greenhouse", "alleninstitute")]),
    ("Fred Hutch", "https://www.fredhutch.org/en/about/careers.html", [("workday", "fredhutch/fredhutch")]),
    ("Dana-Farber Cancer Institute", "https://careers.dana-farber.org", [("workday", "dfci/DFCI")]),
    ("St. Jude Children's Research Hospital", "https://www.stjude.org/jobs.html", [("workday", "stjude/St_Jude_Careers")]),
    ("Scripps Research", "https://www.scripps.edu/careers", [("workday", "scripps/Scripps_Research")]),
    ("Memorial Sloan Kettering", "https://careers.mskcc.org", [("workday", "mskcc/MSKCC")]),
]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _expand(ats: str, board: str) -> list[tuple[str, str]]:
    """A workday "tenant/site" guess becomes one "host/tenant/site" board per common host."""
    if ats != "workday" or board.count("/") != 1:
        return [(ats, board)]
    tenant, site = board.split("/")
    return [("workday", f"{tenant}.{h}.myworkdayjobs.com/{tenant}/{site}") for h in WORKDAY_HOSTS]


def _find(candidate) -> tuple[str, str, tuple[str, str, int] | None]:
    name, url, guesses = candidate
    for ats, board in guesses:
        for a, b in _expand(ats, board):
            count = ats_detect.probe(a, b)
            if count > 0:
                return name, url, (a, b, count)
    return name, url, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="insert the rows (default: dry run)")
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_find, CANDIDATES))
    found = [(n, u, hit) for n, u, hit in results if hit]
    missing = [n for n, _u, hit in results if not hit]

    from database import SessionLocal
    from models import JobBoard
    from scrapers.board_scraper import api_url
    from scrapers.registry import ScraperRegistry

    db = SessionLocal()
    try:
        coded_apis = {getattr(cls, "API_URL", None): s for s, cls in ScraperRegistry.get_all().items()}
        added, skipped = [], []
        for name, url, (ats, board, count) in found:
            slug = _slug(name)
            row = db.query(JobBoard).filter(JobBoard.ats == ats, JobBoard.board == board).first()
            owner = (row.slug if row else None) or coded_apis.get(api_url(ats, board))
            if owner:
                skipped.append(f"{name}: board already scraped as '{owner}'")
                continue
            if ScraperRegistry.has_coded(slug) or db.query(JobBoard).filter(JobBoard.slug == slug).first():
                skipped.append(f"{name}: slug '{slug}' already taken")
                continue
            added.append(f"{name:32} {ats:10} {count:5} jobs  {board}")
            if args.apply:
                db.add(JobBoard(company_name=name, slug=slug, ats=ats, board=board, careers_url=url, enabled=True))
        if args.apply:
            db.commit()
    finally:
        db.close()

    verb = "Added" if args.apply else "Would add"
    print(f"{verb} {len(added)}:")
    print("\n".join(f"  {line}" for line in added))
    print(f"Skipped {len(skipped)}:")
    print("\n".join(f"  {line}" for line in skipped))
    print(f"No board found for {len(missing)}: {', '.join(missing)}")


if __name__ == "__main__":
    main()
