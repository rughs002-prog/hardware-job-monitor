from job_monitor.matching import is_relevant, tag_job
from job_monitor.models import Job


def test_tags_israel_student_physical_design():
    job = tag_job(Job(company="Example", title="Physical Design Intern", location="Haifa, Israel", url="https://example/job/1"))
    assert {"physical-design", "intern"}.issubset(job.tags)
    assert is_relevant(job)


def test_broad_search_does_not_require_student_title():
    job = tag_job(Job(company="Example", title="Silicon Validation Engineer", location="Herzliya", url="https://example/job/2"))
    assert is_relevant(job)


def test_hebrew_hardware_student_is_tagged():
    job = tag_job(Job(company="IAI", title="סטודנט/ית להנדסת חשמל ואלקטרוניקה",
                      url="https://example", location="יהוד", description="פיתוח חומרה"))
    assert {"student", "board-hardware"}.issubset(job.tags)
    assert is_relevant(job)


def test_excludes_unrelated_role():
    job = tag_job(Job(company="Example", title="Marketing Intern", location="Tel Aviv", url="https://example/job/3"))
    assert not is_relevant(job)


def test_excludes_non_israel_role():
    job = tag_job(Job(company="Example", title="RTL Design Intern", location="Austin, Texas", url="https://example/job/4"))
    assert not is_relevant(job)


def test_entry_level_variants_are_tagged():
    job = tag_job(Job(company="Example", title="New College Graduate FPGA Engineer", location="Israel", url="https://example/job/5"))
    assert {"fpga", "junior"}.issubset(job.tags)


def test_formal_verification_is_distinct_from_design_verification():
    formal = tag_job(Job(company="Apple", title="Formal Verification Intern",
                         location="Haifa", url="https://example/formal"))
    dv = tag_job(Job(company="NVIDIA", title="Design Verification Student",
                     location="Tel Aviv", url="https://example/dv"))
    assert "formal-verification" in formal.tags
    assert "design-verification" in dv.tags
    assert formal.priority == dv.priority == "high"


def test_related_role_is_preserved_but_not_high_priority():
    job = tag_job(Job(company="Example", title="Mechanical Engineer",
                      location="Israel", url="https://example/me"))
    assert job.priority == "related"
    assert is_relevant(job)
