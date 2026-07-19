from job_monitor.adapters import parse_official_job_links


def test_parse_official_links_deduplicates_and_ignores_other_links():
    html = """
    <a href="/en-il/details/200640246-0881/verification-student">Verification Student</a>
    <a href="/en-il/details/200640246-0881/verification-student"><span>Verification Student</span></a>
    <a href="/en-il/search">Search</a>
    """
    links = parse_official_job_links(html, r"/en-il/details/[0-9]+-[0-9]+/")
    assert links == [("/en-il/details/200640246-0881/verification-student", "Verification Student")]
