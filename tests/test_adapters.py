from job_monitor.adapters import AmazonJobsAdapter, ComeetAdapter, ElbitJobsAdapter, GoogleCareersHtmlAdapter, IaiJobsAdapter, MobileyeHtmlAdapter, ValensHtmlAdapter, WorkdayAdapter, parse_official_job_links


def test_parse_official_links_deduplicates_and_ignores_other_links():
    html = """
    <a href="/en-il/details/200640246-0881/verification-student">Verification Student</a>
    <a href="/en-il/details/200640246-0881/verification-student"><span>Verification Student</span></a>
    <a href="/en-il/search">Search</a>
    """
    links = parse_official_job_links(html, r"/en-il/details/[0-9]+-[0-9]+/")
    assert links == [("/en-il/details/200640246-0881/verification-student", "Verification Student")]


def test_amazon_adapter_uses_official_country_filter(monkeypatch):
    seen = []

    def fake_request(url):
        seen.append(url)
        return {"hits": 1, "jobs": [{"id": "123", "title": "Hardware Intern",
                                      "location": "IL, Haifa", "job_path": "/en/jobs/123/test"}]}

    monkeypatch.setattr("job_monitor.adapters.request_json", fake_request)
    company = {"name": "Amazon", "source": {"endpoint": "https://www.amazon.jobs/en/search.json",
                                                "country": "ISR", "page_size": 100}}
    jobs = AmazonJobsAdapter().fetch(company)
    assert "country=ISR" in seen[0]
    assert jobs[0].location == "IL, Haifa, Israel"
    assert jobs[0].external_id == "123"


def test_mobileye_adapter_reads_embedded_official_job_links(monkeypatch):
    html = '<script>"url":"/jobs/physical-design-student/12345678-1234-1234-1234-123456789abc"</script>'
    monkeypatch.setattr("job_monitor.adapters.request_text", lambda _: html)
    company = {"name": "Mobileye", "source": {"base_url": "https://careers.mobileye.com",
                                                  "search_url": "https://careers.mobileye.com/jobs"}}
    jobs = MobileyeHtmlAdapter().fetch(company)
    assert jobs[0].title == "Physical Design Student"
    assert jobs[0].external_id == "12345678-1234-1234-1234-123456789abc"


def test_google_adapter_reads_embedded_official_job_links(monkeypatch):
    html = '<script>"jobs/results/123456-hardware-engineering-intern?location=Israel"</script>'
    monkeypatch.setattr("job_monitor.adapters.request_text", lambda _: html)
    company = {"name": "Google", "source": {
        "base_url": "https://www.google.com/about/careers/applications/",
        "search_url": "https://www.google.com/about/careers/applications/jobs/results/?location=Israel",
    }}
    jobs = GoogleCareersHtmlAdapter().fetch(company)
    assert jobs[0].title == "Hardware Engineering Intern"
    assert jobs[0].external_id == "123456"


def test_workday_keeps_first_page_total_when_later_pages_report_zero(monkeypatch):
    calls = []

    def fake_request(_url, payload):
        calls.append(payload["offset"])
        if payload["offset"] == 0:
            return {"total": 3, "jobPostings": [{"title": "RTL Intern", "externalPath": "/job/1"},
                                                   {"title": "ASIC Student", "externalPath": "/job/2"}]}
        return {"total": 0, "jobPostings": [{"title": "FPGA Intern", "externalPath": "/job/3"}]}

    monkeypatch.setattr("job_monitor.adapters.request_json", fake_request)
    company = {"name": "Example", "source": {"base_url": "https://example.wd1.myworkdayjobs.com",
                                                  "tenant": "example", "site": "Careers"}}
    jobs = WorkdayAdapter().fetch(company)
    assert calls == [0, 2]
    assert len(jobs) == 3


def test_workday_incremental_stops_after_known_pages(monkeypatch):
    calls = []

    def fake_request(_url, payload):
        offset = payload["offset"]
        calls.append(offset)
        ids = [f"/job/{offset + n}" for n in range(20)]
        return {"total": 200, "jobPostings": [{"title": "Engineer", "externalPath": item} for item in ids]}

    monkeypatch.setattr("job_monitor.adapters.request_json", fake_request)
    known = {f"/job/{n}" for n in range(100)}
    company = {"name": "Example", "_incremental": True, "_known_external_ids": known,
               "source": {"base_url": "https://example.wd1.myworkdayjobs.com", "tenant": "example",
                          "site": "Careers", "stop_after_known_pages": 3}}
    assert len(WorkdayAdapter().fetch(company)) == 60
    assert calls == [0, 20, 40]


def test_valens_adapter_reads_verified_location(monkeypatch):
    listing = '<a href="https://www.valens.com/position/validation-student/">Validation Student</a>'
    detail = '<div class="location"><span>Valens HQ, Hod Hasharon, Israel</span></div>'
    monkeypatch.setattr("job_monitor.adapters.request_text", lambda url: detail if "/position/" in url else listing)
    company = {"name": "Valens", "source": {"base_url": "https://www.valens.com",
                                                "search_url": "https://www.valens.com/careers/"}}
    jobs = ValensHtmlAdapter().fetch(company)
    assert jobs[0].title == "Validation Student"
    assert jobs[0].location == "Valens HQ, Hod Hasharon, Israel"


def test_comeet_adapter_reads_embedded_positions(monkeypatch):
    data = [{"name": "Physical Design Student", "location": {"name": "Haifa", "country": "IL"},
             "url_comeet_hosted_page": "https://www.comeet.com/jobs/example/A1/job/B2",
             "time_updated": "2026-07-20T00:00:00Z", "details": {"description": "ASIC implementation"}}]
    html = f"<script>COMPANY_POSITIONS_DATA = {__import__('json').dumps(data)};</script>"
    monkeypatch.setattr("job_monitor.adapters.request_text", lambda _: html)
    company = {"name": "Example", "source": {"board_url": "https://www.comeet.com/jobs/example/A1"}}
    jobs = ComeetAdapter().fetch(company)
    assert jobs[0].title == "Physical Design Student"
    assert jobs[0].location == "Haifa, IL, Israel"
    assert jobs[0].external_id == "B2"


def test_iai_adapter_reads_official_feed(monkeypatch):
    seen = []
    def fake_json(url):
        seen.append(url)
        return [{
            "id": 76048334, "tl": "סטודנט/ית להנדסת חשמל ואלקטרוניקה",
            "ct": "יהוד", "dc": "פיתוח חומרה", "tp": "משרה חלקית",
        }]
    monkeypatch.setattr("job_monitor.adapters.request_json", fake_json)
    company = {"name": "IAI", "source": {"base_url": "https://jobs.iai.co.il", "feed_url": "https://jobs.iai.co.il/jobs.json?v=monitor"}}
    job = IaiJobsAdapter().fetch(company)[0]
    assert seen == ["https://jobs.iai.co.il/jobs.json?v=monitor"]
    assert job.external_id == "76048334"
    assert job.url == "https://jobs.iai.co.il/job/76048334/"
    assert job.location == "יהוד"


def test_elbit_adapter_reads_official_feed(monkeypatch):
    monkeypatch.setattr("job_monitor.adapters.request_json", lambda _: [{
        "jobId": 20811, "jobCode": "6970", "jobTitle": "Electrical Engineering Student",
        "description": "&lt;b&gt;Hardware team&lt;/b&gt;", "area": "Center",
        "openDate": "2026-07-12T07:16:00", "extendedProperties": [],
    }])
    company = {"name": "Elbit", "source": {"feed_url": "feed", "board_url": "https://elbitsystemscareer.com/jobs"}}
    job = ElbitJobsAdapter().fetch(company)[0]
    assert job.external_id == "6970"
    assert job.location == "Center, Israel"
    assert job.description == "Hardware team"
