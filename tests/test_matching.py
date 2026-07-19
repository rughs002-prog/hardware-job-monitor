from job_monitor.matching import is_relevant, tag_job
from job_monitor.models import Job


def test_tags_israel_student_physical_design():
    job = tag_job(Job(company="Example", title="Physical Design Intern", location="Haifa, Israel", url="https://example/job/1"))
    assert {"physical-design", "intern"}.issubset(job.tags)
    assert is_relevant(job)


def test_broad_search_does_not_require_student_title():
    job = tag_job(Job(company="Example", title="Silicon Validation Engineer", location="Herzliya", url="https://example/job/2"))
    assert is_relevant(job)


def test_excludes_unrelated_role():
    job = tag_job(Job(company="Example", title="Marketing Intern", location="Tel Aviv", url="https://example/job/3"))
    assert not is_relevant(job)


def test_excludes_non_israel_role():
    job = tag_job(Job(company="Example", title="RTL Design Intern", location="Austin, Texas", url="https://example/job/4"))
    assert not is_relevant(job)


def test_entry_level_variants_are_tagged():
    job = tag_job(Job(company="Example", title="New College Graduate FPGA Engineer", location="Israel", url="https://example/job/5"))
    assert {"fpga", "entry-level"}.issubset(job.tags)
