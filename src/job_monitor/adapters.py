from __future__ import annotations

from abc import ABC, abstractmethod
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urljoin

from .http import request_json, request_text
from .models import Job


def plain(value: str | None) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


class Adapter(ABC):
    @abstractmethod
    def fetch(self, company: dict[str, Any]) -> list[Job]: ...


class GreenhouseAdapter(Adapter):
    def fetch(self, company: dict[str, Any]) -> list[Job]:
        token = company["source"]["board_token"]
        data = request_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        return [Job(company=company["name"], title=j["title"], url=j["absolute_url"],
                    location=(j.get("location") or {}).get("name", ""), description=plain(j.get("content")),
                    external_id=str(j["id"]), posted_at=j.get("updated_at", ""), source="greenhouse", raw=j)
                for j in data.get("jobs", [])]


class LeverAdapter(Adapter):
    def fetch(self, company: dict[str, Any]) -> list[Job]:
        site = company["source"]["site"]
        data = request_json(f"https://api.lever.co/v0/postings/{site}?mode=json")
        return [Job(company=company["name"], title=j["text"], url=j["hostedUrl"],
                    location=(j.get("categories") or {}).get("location", ""),
                    description=plain(" ".join((j.get("descriptionPlain", ""), j.get("additionalPlain", "")))),
                    external_id=j["id"], source="lever", raw=j) for j in data]


class ComeetAdapter(Adapter):
    """Read the official Comeet company board's embedded position data."""

    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        html_text = request_text(src["board_url"])
        marker = "COMPANY_POSITIONS_DATA = "
        start = html_text.find(marker)
        if start < 0:
            raise ValueError("Comeet position data was not found")
        data, _ = json.JSONDecoder().raw_decode(html_text[start + len(marker):].lstrip())
        jobs = []
        for j in data:
            location_data = j.get("location") or {}
            country = location_data.get("country", "")
            location = ", ".join(filter(None, (location_data.get("name"), location_data.get("city"), country)))
            if country.upper() == "IL" and "israel" not in location.lower():
                location = f"{location}, Israel"
            url = j.get("url_comeet_hosted_page") or j.get("url_active_page") or src["board_url"]
            external_id = str(j.get("uid") or j.get("position_uid") or url.rstrip("/").rsplit("/", 1)[-1])
            jobs.append(Job(
                company=company["name"], title=j.get("name", ""), url=url, location=location,
                description=plain(json.dumps(j.get("details") or j, ensure_ascii=False)),
                external_id=external_id, posted_at=j.get("time_updated", ""), source="comeet", raw=j,
            ))
        return jobs


class SmartRecruitersAdapter(Adapter):
    def fetch(self, company: dict[str, Any]) -> list[Job]:
        slug = company["source"]["company_slug"]
        offset, jobs = 0, []
        while True:
            data = request_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
            batch = data.get("content", [])
            jobs.extend(Job(company=company["name"], title=j["name"],
                            url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                            location=", ".join(filter(None, ((j.get("location") or {}).get("city"),
                                                              (j.get("location") or {}).get("country")))),
                            external_id=j["id"], posted_at=j.get("releasedDate", ""),
                            source="smartrecruiters", raw=j) for j in batch)
            offset += len(batch)
            if not batch or offset >= data.get("totalFound", 0):
                return jobs


class AmazonJobsAdapter(Adapter):
    """Official Amazon Jobs JSON feed, restricted to a configured country."""

    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        limit = int(src.get("page_size", 100))
        offset, jobs = 0, []
        while True:
            separator = "&" if "?" in src["endpoint"] else "?"
            url = f"{src['endpoint']}{separator}country={src.get('country', 'ISR')}&result_limit={limit}&offset={offset}"
            data = request_json(url)
            batch = data.get("jobs", [])
            for j in batch:
                location = j.get("location", "")
                if "israel" not in location.lower():
                    location = f"{location}, Israel".strip(", ")
                jobs.append(Job(
                    company=company["name"], title=j.get("title", ""),
                    url=urljoin(src.get("base_url", "https://www.amazon.jobs"), j.get("job_path", "")),
                    location=location,
                    description=plain(" ".join((j.get("description", ""), j.get("basic_qualifications", ""),
                                                  j.get("preferred_qualifications", "")))),
                    external_id=str(j.get("id") or j.get("job_path", "")),
                    posted_at=j.get("posted_date", ""), source="amazon-jobs", raw=j,
                ))
            offset += len(batch)
            total = int(data.get("hits", 0))
            if not batch or offset >= total or offset >= int(src.get("max_results", 1000)):
                return jobs


class WorkdayAdapter(Adapter):
    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        base = src["base_url"].rstrip("/")
        endpoint = f"{base}/wday/cxs/{src['tenant']}/{src['site']}/jobs"
        known = set(company.get("_known_external_ids", ()))
        incremental = bool(company.get("_incremental") and known)
        stop_after_known_pages = int(src.get("stop_after_known_pages", 3))
        offset, jobs, total, known_page_streak = 0, [], None, 0
        while True:
            data = request_json(endpoint, payload={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
            if total is None:
                total = int(data.get("total", 0))
            batch = data.get("jobPostings", [])
            batch_ids = []
            for j in batch:
                path = j.get("externalPath", "")
                external_id = path or j.get("bulletFields", [""])[0]
                batch_ids.append(external_id)
                jobs.append(Job(company=company["name"], title=j.get("title", ""), url=f"{base}/en-US/{src['site']}{path}",
                                location=j.get("locationsText", ""), external_id=external_id,
                                posted_at=j.get("postedOn", ""), source="workday", raw=j))
            offset += len(batch)
            if incremental and batch_ids and all(item_id in known for item_id in batch_ids):
                known_page_streak += 1
            else:
                known_page_streak = 0
            if incremental and known_page_streak >= stop_after_known_pages:
                return jobs
            if not batch or offset >= total or offset >= src.get("max_results", 1000):
                return jobs


class _OfficialJobLinkParser(HTMLParser):
    def __init__(self, href_pattern: str):
        super().__init__()
        self.pattern = re.compile(href_pattern)
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href") or ""
        if self.pattern.search(href):
            self.current_href, self.current_text = href, []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            title = plain(" ".join(self.current_text))
            if title:
                self.links.append((self.current_href, title))
            self.current_href, self.current_text = None, []


def parse_official_job_links(html_text: str, href_pattern: str) -> list[tuple[str, str]]:
    parser = _OfficialJobLinkParser(href_pattern)
    parser.feed(html_text)
    return list(dict.fromkeys(parser.links))


class OfficialHtmlAdapter(Adapter):
    """Conservative fallback for server-rendered official career result pages."""

    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        urls = list(src.get("search_urls", []))
        template = src.get("page_url_template")
        if template:
            urls.extend(template.format(page=page) for page in range(1, int(src.get("max_pages", 1)) + 1))
        jobs: dict[str, Job] = {}
        id_pattern = re.compile(src["id_pattern"])
        for search_url in urls:
            for href, title in parse_official_job_links(request_text(search_url), src["href_pattern"]):
                absolute = urljoin(src["base_url"], href)
                match = id_pattern.search(href)
                external_id = match.group(1) if match else absolute
                jobs.setdefault(external_id, Job(company=company["name"], title=title, url=absolute,
                                                 location=src.get("location", "Israel"), external_id=external_id,
                                                 source="official-html"))
        return list(jobs.values())


class MobileyeHtmlAdapter(Adapter):
    """Extract Mobileye's official job URLs from its embedded page data."""

    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        html_text = request_text(src["search_url"])
        pattern = re.compile(r"/jobs/([^/\"'< ]+)/([0-9a-f-]{36})")
        jobs: dict[str, Job] = {}
        for match in pattern.finditer(html_text):
            slug, external_id = match.groups()
            title = plain(slug.replace("-", " ")).title()
            jobs.setdefault(external_id, Job(
                company=company["name"], title=title,
                url=urljoin(src["base_url"], match.group(0)), location="Israel",
                external_id=external_id, source="official-html",
            ))
        return list(jobs.values())


class GoogleCareersHtmlAdapter(Adapter):
    """Extract official Google Careers results embedded in the Israel results page."""

    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        html_text = request_text(src["search_url"])
        pattern = re.compile(r"jobs/results/([0-9]+)-([^?\"'< ]+)")
        jobs: dict[str, Job] = {}
        for match in pattern.finditer(html_text):
            external_id, slug = match.groups()
            title = plain(slug.replace("-", " ")).title()
            path = f"jobs/results/{external_id}-{slug}"
            jobs.setdefault(external_id, Job(
                company=company["name"], title=title,
                url=urljoin(src["base_url"], path), location="Israel",
                external_id=external_id, source="official-html",
            ))
        return list(jobs.values())


class ValensHtmlAdapter(Adapter):
    """Read Valens' official listing and verify location from each job page."""

    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        listing = request_text(src["search_url"])
        links = parse_official_job_links(listing, r"/position/[^/]+/")
        jobs = []
        for href, title in links:
            url = urljoin(src["base_url"], href)
            detail = request_text(url)
            location_match = re.search(
                r'<div[^>]+class="location"[^>]*>.*?<span[^>]*>(.*?)</span>', detail, re.I | re.S
            )
            location = plain(location_match.group(1)) if location_match else ""
            id_match = re.search(r"/position/([^/]+)/", href)
            jobs.append(Job(
                company=company["name"], title=title, url=url, location=location,
                description=plain(detail), external_id=id_match.group(1) if id_match else url,
                source="official-html",
            ))
        return jobs


ADAPTERS: dict[str, type[Adapter]] = {
    "comeet": ComeetAdapter,
    "amazon-jobs": AmazonJobsAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "workday": WorkdayAdapter,
    "official-html": OfficialHtmlAdapter,
    "mobileye-html": MobileyeHtmlAdapter,
    "google-careers-html": GoogleCareersHtmlAdapter,
    "valens-html": ValensHtmlAdapter,
}
