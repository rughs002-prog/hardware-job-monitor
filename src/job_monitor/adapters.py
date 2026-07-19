from __future__ import annotations

from abc import ABC, abstractmethod
from html import unescape
from html.parser import HTMLParser
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


class WorkdayAdapter(Adapter):
    def fetch(self, company: dict[str, Any]) -> list[Job]:
        src = company["source"]
        base = src["base_url"].rstrip("/")
        endpoint = f"{base}/wday/cxs/{src['tenant']}/{src['site']}/jobs"
        offset, jobs = 0, []
        while True:
            data = request_json(endpoint, payload={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
            batch = data.get("jobPostings", [])
            for j in batch:
                path = j.get("externalPath", "")
                jobs.append(Job(company=company["name"], title=j.get("title", ""), url=f"{base}/en-US/{src['site']}{path}",
                                location=j.get("locationsText", ""), external_id=path or j.get("bulletFields", [""])[0],
                                posted_at=j.get("postedOn", ""), source="workday", raw=j))
            offset += len(batch)
            if not batch or offset >= data.get("total", 0) or offset >= src.get("max_results", 1000):
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


ADAPTERS: dict[str, type[Adapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "workday": WorkdayAdapter,
    "official-html": OfficialHtmlAdapter,
}
