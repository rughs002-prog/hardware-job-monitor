from __future__ import annotations

import re
from collections import Counter

from .models import Job


ROLE_TAGS: dict[str, tuple[str, ...]] = {
    "rtl": ("rtl", "logic design", "digital design", "microarchitecture", "chip design",
            "silicon design", "asic design", "soc design", "front-end design"),
    "physical-design": ("physical design", "physical implementation", "backend vlsi",
                        "back-end vlsi", "place and route", "pnr engineer"),
    "formal-verification": ("formal verification", "formal methods", "property checking",
                            "model checking", "jaspergold", "vc formal"),
    "design-verification": ("design verification", "pre-silicon verification",
                            "functional verification", "verification engineer", "uvm",
                            "systemverilog", "testbench"),
    "validation": ("validation", "post-silicon", "hardware validation", "silicon validation",
                   "characterization"),
    "fpga": ("fpga",),
    "embedded": ("embedded", "real-time", "rtos", "bare metal"),
    "firmware": ("firmware", "low-level software", "device driver", "bios", "bootloader"),
    "board-hardware": ("board design", "pcb", "signal integrity", "hardware engineer",
                       "hardware engineering", "electrical engineer", "electrical engineering",
                       "electronics", "board bring-up", "חומרה", "הנדסת חשמל", "מהנדס חשמל",
                       "אלקטרוניקה", "תכנון כרטיס"),
    "analog-mixed-signal": ("analog", "mixed signal", "mixed-signal", "ams", "serdes",
                            "pll", "adc", "dac"),
    "rf": ("radio frequency", "rf engineer", "rf design", "antenna", "microwave"),
    "signal-processing": ("signal processing", "dsp engineer", "image processing"),
    "cad-eda": ("cad engineer", "eda", "design automation", "vlsi cad"),
    "power": ("power electronics", "power engineer", "power supply", "power integrity",
              "high voltage"),
    "integration": ("system integration", "integration engineer", "integration student",
                    "system engineer"),
    "mechanical": ("mechanical engineer", "mechanical engineering", "mechatronics",
                   "thermal engineer", "הנדסת מכונות"),
    "software-other": ("software engineer", "software engineering", "software developer", "backend engineer",
                       "cloud engineer", "machine learning", "data scientist", "devops"),
}

LEVEL_TAGS: dict[str, tuple[str, ...]] = {
    "student": ("student", "working student", "student engineer", "סטודנט", "סטודנטית"),
    "intern": ("intern", "internship", "co-op", "coop", "summer intern", "university intern",
               "התמחות", "מתמחה"),
    "junior": ("junior", "entry level", "entry-level", "new college graduate",
               "university graduate", "graduate engineer"),
}

ISRAEL_TERMS = (
    "israel", "tel aviv", "tel-aviv", "haifa", "herzliya", "petah tikva", "petach tikva",
    "ra'anana", "raanana", "rannana", "yokneam", "caesarea", "jerusalem", "kiryat gat",
    "beer sheva", "be'er sheva", "hod hasharon", "netanya", "rehovot", "ramat gan",
    "rosh haayin", "kfar saba", "bnei brak", "airport city", "ישראל", "יהוד", "לוד",
    "אשדוד", "באר יעקב", "קריית ביאליק", "כרמיאל", "מודיעין",
)

CENTRAL_ISRAEL_TERMS = (
    "tel aviv", "tel-aviv", "herzliya", "petah tikva", "petach tikva", "ra'anana",
    "raanana", "rannana", "hod hasharon", "netanya", "rehovot", "ramat gan",
    "rosh haayin", "kfar saba", "bnei brak", "airport city", "holon", "bat yam",
    "rishon lezion", "rishon le-zion", "or yehuda", "shoham", "modiin", "modi'in",
    "yehud", "lod", "tel-avis", "תל אביב", "הרצליה", "פתח תקווה", "רעננה",
    "הוד השרון", "נתניה", "רחובות", "רמת גן", "ראש העין", "כפר סבא",
    "בני ברק", "חולון", "בת ים", "ראשון לציון", "אור יהודה", "שוהם",
    "מודיעין", "יהוד", "לוד",
)

CV_CONTEXT = {
    "cv-digital-foundations": ("digital design", "logic design", "computer architecture", "cpu", "assembly"),
    "cv-c-programming": (" c ", "c programming", "firmware", "embedded"),
    "cv-vlsi-direction": ("vlsi", "asic", "physical design", "rtl", "chip design"),
}

PRIORITY_CATEGORIES = {
    "rtl", "physical-design", "formal-verification", "design-verification", "validation",
    "fpga", "embedded", "firmware", "board-hardware", "analog-mixed-signal", "rf",
    "signal-processing", "cad-eda", "power",
}


def _contains(text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def is_israel_job(job: Job) -> bool:
    haystack = f" {job.location} {job.title} {job.description} ".lower()
    return any(_contains(haystack, term) for term in ISRAEL_TERMS)


def is_central_israel_job(job: Job) -> bool:
    haystack = f" {job.location} {job.title} ".lower()
    return any(_contains(haystack, term) for term in CENTRAL_ISRAEL_TERMS)


def tag_job(job: Job) -> Job:
    text = f" {job.title} {job.description} ".lower()
    title = f" {job.title} ".lower()
    roles = [tag for tag, terms in ROLE_TAGS.items() if any(_contains(text, term) for term in terms)]
    levels = [tag for tag, terms in LEVEL_TAGS.items() if any(_contains(title, term) for term in terms)]
    job.tags = roles + levels
    job.relevance = [tag for tag, terms in CV_CONTEXT.items() if any(_contains(text, term) for term in terms)]
    israel = is_israel_job(job)
    central = is_central_israel_job(job)
    job.inclusion_reasons = (["israel-location"] if israel else [])
    job.inclusion_reasons += [f"category:{tag}" for tag in roles]
    job.inclusion_reasons += [f"career-level:{tag}" for tag in levels]
    job.exclusion_reasons = []
    if not israel:
        job.exclusion_reasons.append("outside-or-unknown-israel-location")
    elif central:
        job.inclusion_reasons.append("central-israel-location")
    else:
        job.exclusion_reasons.append("outside-central-israel")
    if not roles:
        job.exclusion_reasons.append("no-related-role-keyword")
    if not levels:
        job.exclusion_reasons.append("no-student-intern-junior-title")
    if israel and central and PRIORITY_CATEGORIES.intersection(roles) and levels:
        job.priority = "high"
    elif israel and roles:
        job.priority = "related"
    else:
        job.priority = "excluded"
    return job


def is_relevant(job: Job) -> bool:
    return job.priority != "excluded"


def reason_counts(jobs: list[Job], included: bool) -> dict[str, int]:
    values = (reason for job in jobs
              for reason in (job.inclusion_reasons if included else job.exclusion_reasons))
    return dict(Counter(values).most_common())
