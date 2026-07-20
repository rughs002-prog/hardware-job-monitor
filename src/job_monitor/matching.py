from __future__ import annotations

import re

from .models import Job


ROLE_TAGS: dict[str, tuple[str, ...]] = {
    "chip-design": ("chip design", "silicon design", "asic", "soc design", "תכנון שבבים", "תכן שבבים"),
    "physical-design": ("physical design", "physical implementation", "back-end", "backend vlsi", "place and route"),
    "rtl": ("rtl", "logic design", "digital design", "microarchitecture", "תכן לוגי", "תכנון לוגי"),
    "verification": ("verification", "pre-silicon", "formal verification", "uvm", "systemverilog", "וריפיקציה", "אימות תכן"),
    "validation": ("validation", "post-silicon", "hardware validation", "characterization", "ולידציה", "אימות חומרה"),
    "fpga": ("fpga",),
    "firmware": ("firmware", "low-level software", "device driver", "embedded software"),
    "embedded": ("embedded", "real-time", "rtos"),
    "analog-mixed-signal": ("analog", "mixed signal", "mixed-signal", "ams", "rf", "serdes", "אנלוגי", "אלקטרואופטיקה"),
    "cad-eda": ("cad engineer", "eda", "design automation", "vlsi cad"),
    "dft": ("design for test", "dft", "scan insertion", "atpg"),
    "board-hardware": ("board design", "pcb", "signal integrity", "hardware engineer", "hardware engineering",
                       "electrical engineer", "electrical engineering", "motion control", "electronics",
                       "חומרה", "הנדסת חשמל", "מהנדס חשמל", "אלקטרוניקה", "תכנון כרטיס", "תכן כרטיס"),
}

LEVEL_TAGS: dict[str, tuple[str, ...]] = {
    "student": ("student", "working student", "student engineer", "סטודנט", "סטודנטית", "סטודנט/ית", "סטודנט.ית"),
    "intern": ("intern", "internship", "co-op", "coop", "summer intern", "university intern", "התמחות", "מתמחה"),
    "entry-level": ("junior", "entry level", "entry-level", "new college graduate", "university graduate", "graduate engineer"),
}

ISRAEL_TERMS = (
    "israel", "tel aviv", "tel-aviv", "haifa", "herzliya", "petah tikva", "petach tikva",
    "ra'anana", "raanana", "yokneam", "caesarea", "jerusalem", "kiryat gat", "beer sheva",
    "be'er sheva", "hod hasharon", "netanya", "rehovot", "ramat gan", "rosh haayin",
    "ישראל", "יהוד", "לוד", "אשדוד", "באר יעקב", "קריית ביאליק", "כרמיאל", "מודיעין",
)

CV_CONTEXT = {
    "cv-digital-foundations": ("digital design", "logic design", "computer architecture", "cpu", "assembly"),
    "cv-c-programming": (" c ", "c programming", "firmware", "embedded"),
    "cv-vlsi-direction": ("vlsi", "asic", "physical design", "rtl", "chip design"),
}


def _contains(text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def is_israel_job(job: Job) -> bool:
    haystack = f" {job.location} {job.title} {job.description} ".lower()
    return any(_contains(haystack, term) for term in ISRAEL_TERMS)


def tag_job(job: Job) -> Job:
    text = f" {job.title} {job.description} ".lower()
    title = f" {job.title} ".lower()
    role_tags = [tag for tag, terms in ROLE_TAGS.items() if any(_contains(text, term) for term in terms)]
    # Alert levels must be explicit in the title. Descriptions often contain generic
    # internship language even for senior roles, which would create false alerts.
    level_tags = [tag for tag, terms in LEVEL_TAGS.items() if any(_contains(title, term) for term in terms)]
    job.tags = role_tags + level_tags
    job.relevance = [tag for tag, terms in CV_CONTEXT.items() if any(_contains(text, term) for term in terms)]
    return job


def is_relevant(job: Job) -> bool:
    """Broad inclusion: require Israel plus one role tag; do not reject on experience."""
    return is_israel_job(job) and any(tag in ROLE_TAGS for tag in job.tags)
