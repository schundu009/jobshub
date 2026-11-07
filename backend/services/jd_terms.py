"""
What a job is, from the words its description uses.

Words like "infrastructure", "platform", "reliability", "production", "automation" and "systems"
mean different jobs in different fields: Teradyne's "Power Infrastructure Engineer" designs tester
power subassemblies, and a plant's "Reliability Engineer" runs FMEAs on pumps. For a title that
only says such a word, the description settles it: physical-engineering terminology with little
software or infrastructure terminology means the job is not a software or DevOps role.

A title that names the field ("DevOps Engineer", "Cloud Engineer", "Software Engineer") is never
overruled, and a missing or stub description changes nothing.
"""
from __future__ import annotations

import html
import re
from typing import Iterable, Optional

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[^a-z0-9+#/]+")


def _compile(terms: Iterable[str]) -> list[tuple[str, re.Pattern]]:
    return [(t, re.compile(r"(?<![a-z0-9])" + re.escape(t).replace(r"\ ", " ") + r"(?![a-z0-9])")) for t in terms]


# The tools and practices of software, DevOps, SRE and cloud work.
_SOFTWARE = _compile((
    "kubernetes", "k8s", "docker", "containers", "containerization", "terraform", "ansible", "helm", "pulumi",
    "ci/cd", "ci cd", "cicd", "jenkins", "github actions", "gitlab", "argocd", "argo cd", "gitops", "devops",
    "sre", "site reliability", "slo", "slos", "sli", "error budget", "on call", "incident response", "postmortem",
    "prometheus", "grafana", "datadog", "splunk", "opentelemetry", "observability", "new relic",
    "aws", "azure", "gcp", "google cloud", "cloud infrastructure", "cloud native", "ec2", "s3", "lambda",
    "infrastructure as code", "microservices", "distributed systems", "rest api", "apis", "linux", "unix",
    "python", "golang", "java", "javascript", "typescript", "rust", "c++", "c#", "bash", "shell scripting",
    "sql", "postgresql", "mysql", "redis", "kafka", "software engineering", "software development", "source code",
    "git", "virtualization", "vmware", "openshift", "networking", "tcp/ip", "dns",
))

# Words only SRE work uses. A "Reliability" title whose description says these is SRE, however few tools it lists.
_SRE = _compile(("sre", "site reliability", "slo", "slos", "sli", "error budget", "postmortem", "observability"))

# Designing circuits and electronic hardware.
_ELECTRONICS = _compile((
    "electrical engineering", "electronics engineering", "electromechanical", "power electronics", "power supply",
    "power supplies", "power delivery", "power subassembly", "subassembly", "emc", "emi", "pcb", "printed circuit",
    "schematic", "schematics", "altium", "cadence allegro", "orcad", "spice", "ltspice", "oscilloscope",
    "soldering", "semiconductor test", "semiconductor testers", "test equipment", "signal integrity",
    "analog circuit", "analog design", "mixed signal", "circuit design", "dc/dc", "ac/dc", "magnetics",
))

# Plants, buildings, grids and machines.
_PHYSICAL = _compile((
    "mechanical engineering", "civil engineering", "structural engineering", "chemical engineering",
    "industrial engineering", "power distribution", "power systems", "switchgear", "power transformer", "power transformers",
    "substation", "substations", "medium voltage", "high voltage", "low voltage", "diesel generators",
    "backup generators", "transmission lines",
    "power grid", "electrical grid", "hvac", "chiller", "chillers", "plumbing", "piping", "welding", "machining",
    "turbine", "turbines", "boiler", "boilers", "compressors", "pumps", "preventive maintenance",
    "predictive maintenance", "fmea", "cmms", "plcs", "plc programming", "scada", "solidworks", "autocad",
    "manufacturing support", "manufacturing process", "manufacturing processes", "production line", "assembly line",
    "shop floor", "plant operations", "avionics", "spacecraft", "propulsion", "mil std", "nec code",
))

# Hardware postings often mention Python or Linux too, so software terms don't settle it alone.
MIN_FIELD_TERMS = 3
# Shorter than this is a stub or a sign-in wall, which says nothing about the job.
MIN_DESCRIPTION_CHARS = 300
# Plain "Reliability Engineer" is hardware or plant work more often than SRE, so it has to show it is SRE.
MIN_RELIABILITY_SOFTWARE_TERMS = 4

_GENERIC_TITLE = re.compile(
    r"(?<![a-z0-9])(?:infrastructure|platform|reliability|production|automation|systems?)(?![a-z0-9])")
_RELIABILITY_ONLY = re.compile(
    r"^(?!.*(?<![a-z0-9])(?:infrastructure|platform|production|automation)(?![a-z0-9])).*(?<![a-z0-9])reliability(?![a-z0-9])")
# Not "production": "Production Engineer" is filed from the title alone, and at Meta it is SRE work.
_MISLEADING_WORD = re.compile(r"(?<![a-z0-9])(?:infrastructure|platform|reliability|automation|systems?)(?![a-z0-9])")
_HARDWARE_TITLE = re.compile(r"(?<![a-z0-9])hardware(?![a-z0-9])")
_ADMIN_TITLE = re.compile(r"(?<![a-z0-9])administrator(?![a-z0-9])")  # looks after machines, doesn't design them
_NAMED_TITLE = re.compile(
    r"(?<![a-z0-9])(?:devops|dev ops|devsecops|sre|site reliability|cloud|kubernetes|k8s|terraform|openshift|"
    r"aws|azure|gcp|software|sw|sde|developer|programmer|data|database|ml|ai|machine learning|security|cyber|"
    r"cybersecurity|network|networking|linux|unix|windows|web|backend|back end|frontend|front end|full stack|"
    r"fullstack|api|observability|release|it|mlops|llm|gpu|storage|salesforce|sap)(?![a-z0-9])")


def _plain(text: str) -> str:
    return _SPACE.sub(" ", _TAG.sub(" ", html.unescape(text)).lower())


def _hits(terms: list[tuple[str, re.Pattern]], text: str) -> int:
    return sum(1 for _t, rx in terms if rx.search(text))


def title_needs_description(title: Optional[str]) -> bool:
    """True when the title only says a word that means different jobs in different fields."""
    t = _plain(title or "").replace("data center", "datacenter")
    return bool(_GENERIC_TITLE.search(t)) and not _NAMED_TITLE.search(t)


def title_word_misleads(title: Optional[str], category: Optional[str]) -> bool:
    """True when a job filed outside IT only looks like IT because of a word in its title,
    such as "infrastructure" in "Power Infrastructure Engineer"."""
    return (category in ("other", "embedded_hw") and title_needs_description(title)
            and bool(_MISLEADING_WORD.search(_plain(title or ""))))


def physical_field(description: Optional[str], title: Optional[str] = None) -> Optional[str]:
    """'electronics' or 'physical' when the title or description says it is that work, else None."""
    plain_title = _plain(title or "")
    if _HARDWARE_TITLE.search(plain_title) and not _ADMIN_TITLE.search(plain_title):
        return "electronics"
    if not description:
        return None
    text = _plain(description)
    if len(text) < MIN_DESCRIPTION_CHARS:
        return None
    electronics, physical = _hits(_ELECTRONICS, text), _hits(_PHYSICAL, text)
    field, software = electronics + physical, _hits(_SOFTWARE, text)
    if not ((field >= MIN_FIELD_TERMS and field > software)
            or (field and not software)
            or (_RELIABILITY_ONLY.search(plain_title) and software < MIN_RELIABILITY_SOFTWARE_TERMS
                and (field or not _hits(_SRE, text)))):
        return None
    return "electronics" if electronics and electronics >= physical else "physical"
