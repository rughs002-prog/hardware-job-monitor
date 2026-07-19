from job_monitor.adapters import AmazonJobsAdapter, GoogleCareersHtmlAdapter, MobileyeHtmlAdapter, parse_official_job_links


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
