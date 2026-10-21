#!/usr/bin/env python3
"""
Add a set of employers as job_boards rows, one set per industry.

  life_sciences  pharma, biotech, genomics, health data, research institutes:
                 the employers behind lifescience.net's listings. That site
                 refuses crawlers (robots.txt: Disallow / for every agent but
                 search engines), so the jobs come from each employer's own
                 board; services.it_roles keeps their computational roles.
  silicon        chip makers, AI chips, EDA, equipment, test, photonics,
                 quantum hardware.

Each candidate names one or more guesses at its board; the first guess whose
public API lists jobs (services.ats_detect.probe) is kept. A board that exists
but lists nothing today is kept too (the company may post later), but only
where its owner can be confirmed without job titles: a Greenhouse board's own
name matching the company, or a Workday tenant (named after the company).
Workday guesses give tenant/site and every common wdN host is tried. A board
already scraped (by a job_boards row or a coded scraper) or a slug already
taken is skipped. The dry run prints sample titles to check each board is the
company meant.

Usage (from backend/):
    python -m tools.add_employer_boards silicon            # dry run: what would be added
    python -m tools.add_employer_boards silicon --apply    # insert the rows
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

import httpx  # noqa: E402

from scrapers.board_scraper import api_url  # noqa: E402
from services import ats_detect  # noqa: E402

WORKDAY_HOSTS = ("wd1", "wd3", "wd5", "wd12", "wd103", "wd501")

# (company name, careers url, [(ats, board), ...]); workday boards are "tenant/site".
LIFE_SCIENCES: list[tuple[str, str, list[tuple[str, str]]]] = [
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

SILICON: list[tuple[str, str, list[tuple[str, str]]]] = [
    # ------------------------------------------------ chip makers
    ("Micron Technology", "https://careers.micron.com", [("workday", "micron/External")]),
    ("Texas Instruments", "https://careers.ti.com", [("workday", "ti/TI"), ("workday", "texasinstruments/TI_Careers")]),
    ("Analog Devices", "https://www.analog.com/en/careers.html", [("workday", "analogdevices/External")]),
    ("NXP Semiconductors", "https://www.nxp.com/careers", [("workday", "nxp/careers")]),
    ("Infineon Technologies", "https://www.infineon.com/careers", [("workday", "infineon/Infineon_Careers"),
                                                                  ("workday", "infineon/External")]),
    ("STMicroelectronics", "https://www.st.com/careers", [("workday", "st/STCareers"), ("workday", "stmicroelectronics/ST")]),
    ("Microchip Technology", "https://www.microchip.com/careers", [("workday", "microchiphr/External"),
                                                                 ("workday", "microchip/External")]),
    ("onsemi", "https://www.onsemi.com/careers", [("workday", "onsemi/onsemi"), ("workday", "onsemi/External")]),
    ("GlobalFoundries", "https://gf.com/careers", [("workday", "globalfoundries/External")]),
    ("Skyworks Solutions", "https://www.skyworksinc.com/careers", [("workday", "skyworks/Skyworks"),
                                                                  ("workday", "skyworks/External")]),
    ("Qorvo", "https://careers.qorvo.com", [("workday", "qorvo/Qorvo_Careers"), ("workday", "qorvo/External")]),
    ("Renesas Electronics", "https://www.renesas.com/careers", [("workday", "renesas/Renesas_External"),
                                                               ("workday", "renesas/External")]),
    ("Cirrus Logic", "https://www.cirrus.com/careers", [("workday", "cirrus/Cirrus_Logic"), ("workday", "cirrus/External")]),
    ("Lattice Semiconductor", "https://www.latticesemi.com/careers", [("workday", "latticesemi/Lattice"),
                                                                     ("workday", "latticesemi/External")]),
    ("Monolithic Power Systems", "https://www.monolithicpower.com/careers", [("workday", "monolithicpower/MPS")]),
    ("Wolfspeed", "https://careers.wolfspeed.com", [("workday", "wolfspeed/Wolfspeed"), ("workday", "wolfspeed/External")]),
    ("Rambus", "https://www.rambus.com/careers", [("workday", "rambus/Rambus"), ("workday", "rambus/External")]),
    ("Silicon Labs", "https://www.silabs.com/careers", [("workday", "silabs/SiliconLabsCareers"), ("workday", "silabs/External")]),
    ("Seagate Technology", "https://www.seagate.com/careers", [("workday", "seagatecareers/Seagate")]),
    ("Allegro MicroSystems", "https://www.allegromicro.com/careers", [("workday", "allegromicro/Allegro"),
                                                                     ("workday", "allegromicro/External")]),
    ("MACOM", "https://www.macom.com/careers", [("workday", "macom/MACOM"), ("workday", "macom/External")]),
    ("Semtech", "https://www.semtech.com/careers", [("workday", "semtech/Semtech"), ("workday", "semtech/SemtechCareers")]),
    ("Power Integrations", "https://www.power.com/careers", [("workday", "power/PowerIntegrations")]),
    ("Diodes Incorporated", "https://www.diodes.com/careers", [("workday", "diodes/Diodes")]),
    ("Navitas Semiconductor", "https://navitassemi.com/careers", [("greenhouse", "navitassemiconductor"), ("lever", "navitassemi")]),
    ("Credo Technology", "https://credosemi.com/careers", [("workday", "credosemi/Credo"), ("greenhouse", "credo")]),
    ("Alphawave Semi", "https://awavesemi.com/careers", [("greenhouse", "alphawavesemi"), ("lever", "alphawave")]),
    ("Ampere Computing", "https://amperecomputing.com/careers", [("workday", "amperecomputing/Ampere"),
                                                                ("greenhouse", "amperecomputing")]),
    ("SiFive", "https://www.sifive.com/careers", [("greenhouse", "sifive"), ("lever", "sifive")]),
    ("Rivos", "https://www.rivosinc.com/careers", [("greenhouse", "rivosinc"), ("ashby", "rivos")]),
    ("Ventana Micro Systems", "https://www.ventanamicro.com/careers", [("greenhouse", "ventanamicrosystems"), ("lever", "ventanamicro")]),
    ("Eliyan", "https://eliyan.com/careers", [("greenhouse", "eliyan"), ("lever", "eliyan")]),
    ("Samsung Semiconductor", "https://semiconductor.samsung.com/us/careers", [("workday", "sec/Samsung_Careers")]),
    # ------------------------------------------------ AI chips
    ("Etched", "https://www.etched.com/careers", [("ashby", "etched"), ("greenhouse", "etched")]),
    ("d-Matrix", "https://www.d-matrix.ai/careers", [("greenhouse", "dmatrix"), ("lever", "d-matrix"), ("ashby", "d-matrix")]),
    ("Lightmatter", "https://lightmatter.co/careers", [("greenhouse", "lightmatter"), ("lever", "lightmatter")]),
    ("Ayar Labs", "https://ayarlabs.com/careers", [("greenhouse", "ayarlabs"), ("lever", "ayarlabs")]),
    ("Celestial AI", "https://www.celestial.ai/careers", [("greenhouse", "celestialai"), ("lever", "celestial-ai")]),
    ("Enfabrica", "https://www.enfabrica.net/careers", [("greenhouse", "enfabrica"), ("lever", "enfabrica")]),
    ("MatX", "https://matx.com/careers", [("ashby", "matx"), ("greenhouse", "matx")]),
    ("Groq", "https://groq.com/careers", [("greenhouse", "groq"), ("ashby", "groq")]),
    ("Untether AI", "https://www.untether.ai/careers", [("lever", "untether"), ("greenhouse", "untetherai")]),
    ("SiMa.ai", "https://sima.ai/careers", [("lever", "sima-ai"), ("greenhouse", "simaai")]),
    ("Axelera AI", "https://axelera.ai/careers", [("greenhouse", "axeleraai"), ("lever", "axelera")]),
    ("EnCharge AI", "https://www.encharge.ai/careers", [("greenhouse", "enchargeai"), ("lever", "encharge")]),
    ("Hailo", "https://hailo.ai/company-overview/careers", [("greenhouse", "hailo"), ("lever", "hailo")]),
    ("Blaize", "https://www.blaize.com/careers", [("greenhouse", "blaize"), ("lever", "blaize")]),
    ("Quadric", "https://quadric.io/careers", [("greenhouse", "quadric"), ("lever", "quadric")]),
    ("Normal Computing", "https://www.normalcomputing.com/careers", [("ashby", "normalcomputing"), ("greenhouse", "normalcomputing")]),
    ("Extropic", "https://www.extropic.ai/careers", [("ashby", "extropic"), ("greenhouse", "extropic")]),
    ("Positron AI", "https://www.positron.ai/careers", [("ashby", "positron"), ("greenhouse", "positronai")]),
    ("Tenstorrent", "https://tenstorrent.com/careers", [("greenhouse", "tenstorrent")]),
    # ------------------------------------------------ EDA, equipment, test, photonics
    ("Synopsys", "https://careers.synopsys.com", [("workday", "synopsys/Careers"), ("workday", "synopsys/External")]),
    ("Cadence Design Systems", "https://www.cadence.com/en_US/home/company/careers.html", [("workday", "cadence/External_Careers"),
                                                                                          ("workday", "cadence/External")]),
    ("Keysight Technologies", "https://jobs.keysight.com", [("workday", "keysight/Keysight")]),
    ("Lam Research", "https://careers.lamresearch.com", [("workday", "lamresearch/LAM"), ("workday", "lam/LAM")]),
    ("ASML", "https://www.asml.com/en/careers", [("workday", "asml/ASML"), ("workday", "asml/External")]),
    ("Teradyne", "https://jobs.teradyne.com", [("workday", "teradyne/Teradyne"), ("workday", "teradyne/External")]),
    ("Cohu", "https://www.cohu.com/careers", [("workday", "cohu/Cohu"), ("workday", "cohu/External")]),
    ("Entegris", "https://www.entegris.com/careers", [("workday", "entegris/EntegrisCareers"), ("workday", "entegris/External")]),
    ("MKS Instruments", "https://www.mks.com/careers", [("workday", "mksinst/MKSCareersUniversal"), ("workday", "mks/External")]),
    ("Onto Innovation", "https://ontoinnovation.com/careers", [("workday", "ontoinnovation/Onto"), ("workday", "ontoinnovation/External")]),
    ("FormFactor", "https://www.formfactor.com/careers", [("workday", "formfactor/FormFactor"), ("workday", "formfactor/External")]),
    ("Amkor Technology", "https://amkor.com/careers", [("workday", "amkor/Amkor"), ("workday", "amkor/External")]),
    ("Coherent", "https://www.coherent.com/company/careers", [("workday", "coherent/Coherent"), ("workday", "coherent/External")]),
    ("Lumentum", "https://www.lumentum.com/en/careers", [("workday", "lumentum/Lumentum"), ("workday", "lumentum/LITE")]),
    ("IPG Photonics", "https://www.ipgphotonics.com/en/careers", [("workday", "ipgphotonics/IPG"), ("workday", "ipgphotonics/External")]),
    ("TTM Technologies", "https://www.ttm.com/careers", [("workday", "ttm/TTM"), ("workday", "ttm/External")]),
    ("Flex", "https://flex.com/careers", [("workday", "flextronics/Careers"), ("workday", "flex/Careers")]),
    ("Zebra Technologies", "https://www.zebra.com/us/en/about-zebra/careers.html", [("workday", "zebra/Zebra_Careers"),
                                                                                   ("workday", "zebra/External")]),
    ("Garmin", "https://careers.garmin.com", [("workday", "garmin/Garmin"), ("workday", "garmin/External")]),
    ("Neuralink", "https://neuralink.com/careers", [("greenhouse", "neuralink")]),
    # ------------------------------------------------ quantum hardware
    ("Quantinuum", "https://www.quantinuum.com/careers", [("greenhouse", "quantinuum"), ("lever", "quantinuum"),
                                                          ("workday", "quantinuum/Quantinuum")]),
    ("Rigetti Computing", "https://www.rigetti.com/careers", [("lever", "rigetti"), ("greenhouse", "rigetti")]),
    ("Atom Computing", "https://atom-computing.com/careers", [("greenhouse", "atomcomputing"), ("lever", "atomcomputing")]),
    ("Infleqtion", "https://infleqtion.com/careers", [("greenhouse", "infleqtion"), ("lever", "infleqtion"), ("ashby", "infleqtion")]),
    ("Xanadu", "https://www.xanadu.ai/careers", [("lever", "xanadu"), ("greenhouse", "xanadu"), ("ashby", "xanadu")]),
    ("Pasqal", "https://www.pasqal.com/careers", [("lever", "pasqal"), ("greenhouse", "pasqal")]),
    ("D-Wave", "https://www.dwavequantum.com/careers", [("greenhouse", "dwavesystems"), ("lever", "dwave"), ("workday", "dwave/DWave")]),
    ("Alice & Bob", "https://alice-bob.com/careers", [("lever", "alice-bob"), ("ashby", "alice-bob"), ("greenhouse", "alicebob")]),
    ("IQM Quantum Computers", "https://www.meetiqm.com/careers", [("greenhouse", "iqm"), ("lever", "iqm")]),
]

SETS = {"life_sciences": LIFE_SCIENCES, "silicon": SILICON}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _expand(ats: str, board: str) -> list[tuple[str, str]]:
    """A workday "tenant/site" guess becomes one "host/tenant/site" board per common host."""
    if ats != "workday" or board.count("/") != 1:
        return [(ats, board)]
    tenant, site = board.split("/")
    return [("workday", f"{tenant}.{h}.myworkdayjobs.com/{tenant}/{site}") for h in WORKDAY_HOSTS]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in ("inc", "the", "llc", "ltd", "co", "corp")}


def _listing(ats: str, board: str) -> tuple[bool, int, list[str], str]:
    """(board exists, job count, a few titles, the board's own name) from its public API."""
    url = api_url(ats, board)
    if not url:
        return False, 0, [], ""
    try:
        with httpx.Client(timeout=ats_detect.TIMEOUT, headers={"User-Agent": ats_detect.USER_AGENT,
                                                               "Accept": "application/json"}) as client:
            if ats == "workday":
                resp = client.post(url, json={"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""})
            else:
                resp = client.get(url)
            if resp.status_code != 200:
                return False, 0, [], ""
            data = resp.json()
            name = ""
            if ats == "greenhouse":
                meta = client.get(url.rsplit("/jobs", 1)[0])
                name = (meta.json() or {}).get("name", "") if meta.status_code == 200 else ""
    except Exception:
        return False, 0, [], ""
    if ats == "lever":
        jobs = data if isinstance(data, list) else None
        titles = [j.get("text", "") for j in (jobs or [])[:3]]
    elif isinstance(data, dict):
        key = "jobPostings" if ats == "workday" else "jobs"
        jobs = data.get(key) if isinstance(data.get(key), list) else None
        titles = [j.get("title", "") for j in (jobs or [])[:3] if isinstance(j, dict)]
    else:
        jobs = None
        titles = []
    if jobs is None:
        return False, 0, [], ""
    return True, ats_detect._job_count(ats, data), titles, name


def _find(candidate):
    """(name, url, (ats, board, count, titles) | None): the first guess with jobs, else an empty board whose owner is clear."""
    name, url, guesses = candidate
    empty = None
    for ats, board in guesses:
        for a, b in _expand(ats, board):
            exists, count, titles, board_name = _listing(a, b)
            if not exists:
                continue
            if count > 0:
                return name, url, (a, b, count, titles)
            owned = a == "workday" or (a == "greenhouse" and _words(name) <= _words(board_name))
            if owned and empty is None:
                empty = (a, b, 0, [f"(empty board: {board_name or 'workday tenant'})"])
    if empty is None:
        # The careers page itself may link or embed its board (ats_detect.detect, the admin's Detect).
        hit = ats_detect.detect(url)
        if hit:
            _exists, count, titles, _n = _listing(hit["ats"], hit["board"])
            return name, url, (hit["ats"], hit["board"], hit["job_count"], titles + ["(from the careers page)"])
    return name, url, empty


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set", choices=sorted(SETS), help="which employers to add")
    parser.add_argument("--apply", action="store_true", help="insert the rows (default: dry run)")
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_find, SETS[args.set]))
    found = [(n, u, hit) for n, u, hit in results if hit]
    missing = [n for n, _u, hit in results if not hit]

    from database import SessionLocal
    from models import JobBoard
    from scrapers.registry import ScraperRegistry

    db = SessionLocal()
    try:
        coded_apis = {getattr(cls, "API_URL", None): s for s, cls in ScraperRegistry.get_all().items()}
        added, skipped = [], []
        for name, url, (ats, board, count, titles) in found:
            slug = _slug(name)
            row = db.query(JobBoard).filter(JobBoard.ats == ats, JobBoard.board == board).first()
            owner = (row.slug if row else None) or coded_apis.get(api_url(ats, board))
            if owner:
                skipped.append(f"{name}: board already scraped as '{owner}'")
                continue
            if ScraperRegistry.has_coded(slug) or db.query(JobBoard).filter(JobBoard.slug == slug).first():
                skipped.append(f"{name}: slug '{slug}' already taken")
                continue
            added.append(f"{name:30} {ats:10} {count:5} jobs  {board}\n{'':44}{' | '.join(titles)[:150]}")
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
