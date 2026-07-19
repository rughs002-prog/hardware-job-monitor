from job_monitor.models import Job
from job_monitor.storage import Store


def test_upsert_detects_new_only_once(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    job = Job(company="Example", title="RTL Intern", url="https://example/jobs/42", external_id="42", tags=["rtl", "intern"])
    assert store.upsert(job) is True
    job.title = "RTL Design Intern"
    assert store.upsert(job) is False
    assert len(store.pending()) == 1
    store.close()


def test_same_external_id_at_different_companies_is_not_duplicate(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    a = Job(company="A", title="FPGA Student", url="https://a/jobs/1", external_id="1")
    b = Job(company="B", title="FPGA Student", url="https://b/jobs/1", external_id="1")
    assert store.upsert(a) is True
    assert store.upsert(b) is True
    store.close()


def test_pending_email_excludes_regular_and_entry_level_roles(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    store.upsert(Job(company="A", title="RTL Engineer", url="https://a/1", tags=["rtl"]))
    store.upsert(Job(company="A", title="Junior RTL Engineer", url="https://a/2", tags=["rtl", "entry-level"]))
    store.upsert(Job(company="A", title="RTL Student", url="https://a/3", tags=["rtl", "student"]))
    store.upsert(Job(company="A", title="RTL Intern", url="https://a/4", tags=["rtl", "intern"]))
    assert {row["title"] for row in store.pending()} == {"RTL Student", "RTL Intern"}
    store.close()


def test_pending_email_excludes_software_only_student_roles(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    store.upsert(Job(company="A", title="Embedded Software Student", url="https://a/1",
                     tags=["firmware", "embedded", "student"]))
    store.upsert(Job(company="A", title="Hardware Validation Student", url="https://a/2",
                     tags=["validation", "student"]))
    assert [row["title"] for row in store.pending()] == ["Hardware Validation Student"]
    store.close()


def test_pending_email_rejects_software_titles_and_deduplicates_locale_variants(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    store.upsert(Job(company="A", title="Software Development Student", url="https://a/1",
                     external_id="1", location="Israel", tags=["board-hardware", "student"]))
    store.upsert(Job(company="Apple", title="Hardware Engineering Student", url="https://a/2",
                     external_id="2", location="Israel", tags=["board-hardware", "student"]))
    store.upsert(Job(company="Apple", title="Hardware Engineering Student", url="https://a/3",
                     external_id="3", location="Israel", tags=["board-hardware", "student"]))
    assert [row["title"] for row in store.pending()] == ["Hardware Engineering Student"]
    store.mark_notified([store.pending()[0]["fingerprint"]])
    assert store.db.execute("SELECT COUNT(*) FROM jobs WHERE notified_at IS NULL").fetchone()[0] == 1
    # The only unnotified row is the deliberately excluded software position.
    assert store.pending() == []
    store.close()
