from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job


ALERT_ROLE_TAGS = {
    "chip-design", "physical-design", "rtl", "verification", "validation", "fpga",
    "analog-mixed-signal", "cad-eda", "dft", "board-hardware",
}
SOFTWARE_TITLE_TERMS = ("software", "firmware", "embedded", "devops", "algorithm", "data scientist", "applied scientist")
NON_HARDWARE_TITLE_TERMS = (
    "administration", "administrative", "accounting", "economics", "finance", "human resources", " hr ",
    "legal", "logistics", "planning and production control", "mechanical engineering", "quality engineering",
    "אדמיניסטרציה", "חשבונאות", "כלכלה", "כספים", "משאבי אנוש", "משפטים", "לוגיסטיקה",
    "הנדסת מכונות", "הנדסת תעשייה וניהול", "איכות",
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 fingerprint TEXT PRIMARY KEY, company TEXT NOT NULL, external_id TEXT, title TEXT NOT NULL,
 url TEXT NOT NULL, location TEXT, description TEXT, posted_at TEXT, source TEXT,
 tags_json TEXT NOT NULL, relevance_json TEXT NOT NULL, first_seen_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL, notified_at TEXT, content_hash TEXT DEFAULT '',
 priority TEXT DEFAULT 'related', inclusion_reasons_json TEXT DEFAULT '[]',
 exclusion_reasons_json TEXT DEFAULT '[]', is_active INTEGER DEFAULT 1, closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs(notified_at, first_seen_at);
CREATE TABLE IF NOT EXISTS scan_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
 company TEXT NOT NULL, status TEXT NOT NULL, found_count INTEGER DEFAULT 0, error TEXT
);
CREATE TABLE IF NOT EXISTS source_items (
 company TEXT NOT NULL, external_id TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 PRIMARY KEY(company, external_id)
);
CREATE TABLE IF NOT EXISTS source_state (
 company TEXT PRIMARY KEY, last_full_scan_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        additions = {
            "content_hash": "TEXT DEFAULT ''",
            "priority": "TEXT DEFAULT 'related'",
            "inclusion_reasons_json": "TEXT DEFAULT '[]'",
            "exclusion_reasons_json": "TEXT DEFAULT '[]'",
            "is_active": "INTEGER DEFAULT 1",
            "closed_at": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def upsert(self, job: Job) -> str:
        now = datetime.now(timezone.utc).isoformat()
        unrelated_title = any(term in f" {job.title.lower()} " for term in NON_HARDWARE_TITLE_TERMS)
        software_only_title = (
            any(term in job.title.lower() for term in SOFTWARE_TITLE_TERMS)
            and not {"embedded", "firmware"}.intersection(job.tags)
        )
        if (job.priority == "related" and not job.inclusion_reasons and not unrelated_title
                and not software_only_title
                and {"student", "intern", "junior", "entry-level"}.intersection(job.tags)):
            role_tags = set(job.tags) - {"student", "intern", "junior", "entry-level"}
            if role_tags - {"software-other", "mechanical", "integration"}:
                job.priority = "high"
        content = "|".join((job.title.strip(), job.location.strip(), job.description.strip(), job.url.strip()))
        content_hash = __import__("hashlib").sha256(content.encode("utf-8")).hexdigest()
        existing = self.db.execute(
            "SELECT content_hash FROM jobs WHERE fingerprint=?", (job.fingerprint,)
        ).fetchone()
        status = "new" if existing is None else (
            "modified" if existing["content_hash"] and existing["content_hash"] != content_hash else "unchanged"
        )
        self.db.execute("""INSERT INTO jobs
            (fingerprint,company,external_id,title,url,location,description,posted_at,source,
             tags_json,relevance_json,first_seen_at,last_seen_at,notified_at,content_hash,
             priority,inclusion_reasons_json,exclusion_reasons_json,is_active,closed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,1,NULL)
            ON CONFLICT(fingerprint) DO UPDATE SET title=excluded.title, url=excluded.url,
            location=excluded.location, description=excluded.description, posted_at=excluded.posted_at,
            tags_json=excluded.tags_json, relevance_json=excluded.relevance_json,
            last_seen_at=excluded.last_seen_at, content_hash=excluded.content_hash,
            priority=excluded.priority, inclusion_reasons_json=excluded.inclusion_reasons_json,
            exclusion_reasons_json=excluded.exclusion_reasons_json, is_active=1, closed_at=NULL""",
            (job.fingerprint, job.company, job.external_id, job.title, job.url, job.location,
             job.description, job.posted_at, job.source, json.dumps(job.tags), json.dumps(job.relevance),
             now, now, content_hash, job.priority, json.dumps(job.inclusion_reasons),
             json.dumps(job.exclusion_reasons)))
        self.db.commit()
        return status

    def mark_closed_missing(self, company: str, seen_fingerprints: set[str]) -> int:
        rows = self.db.execute(
            "SELECT fingerprint FROM jobs WHERE company=? AND is_active=1", (company,)
        )
        missing = [row["fingerprint"] for row in rows if row["fingerprint"] not in seen_fingerprints]
        if missing:
            now = datetime.now(timezone.utc).isoformat()
            self.db.executemany(
                "UPDATE jobs SET is_active=0,closed_at=? WHERE fingerprint=?",
                [(now, fingerprint) for fingerprint in missing],
            )
            self.db.commit()
        return len(missing)

    def pending(self) -> list[sqlite3.Row]:
        rows = self.db.execute("""
            SELECT * FROM jobs
            WHERE notified_at IS NULL
              AND priority='high' AND is_active=1
            ORDER BY first_seen_at
        """)
        pending, seen = [], set()
        for row in rows:
            external_id = row["external_id"] or row["url"]
            if row["company"] == "Apple":
                external_id = external_id.split("-", 1)[0]
            dedupe_key = (row["company"].lower(), external_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            pending.append(row)
        return pending

    def mark_notified(self, fingerprints: list[str]) -> None:
        if not fingerprints:
            return
        now = datetime.now(timezone.utc).isoformat()
        selected = list(self.db.execute(
            f"SELECT company, external_id FROM jobs WHERE fingerprint IN ({','.join('?' for _ in fingerprints)})",
            fingerprints,
        ))
        self.db.executemany("UPDATE jobs SET notified_at=? WHERE fingerprint=?", [(now, fp) for fp in fingerprints])
        for row in selected:
            if row["company"] == "Apple" and row["external_id"]:
                base_id = row["external_id"].split("-", 1)[0]
                self.db.execute(
                    "UPDATE jobs SET notified_at=? WHERE company='Apple' AND external_id LIKE ?",
                    (now, f"{base_id}-%"),
                )
        self.db.commit()

    def scan_start(self, company: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.db.execute("INSERT INTO scan_runs(started_at,company,status) VALUES(?,?,'running')", (now, company))
        self.db.commit()
        return int(cur.lastrowid)

    def source_ids(self, company: str) -> set[str]:
        return {row[0] for row in self.db.execute(
            "SELECT external_id FROM source_items WHERE company=?", (company,)
        )}

    def remember_source_items(self, company: str, jobs: list[Job]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        values = [(company, job.external_id, now) for job in jobs if job.external_id]
        self.db.executemany("""
            INSERT INTO source_items(company, external_id, last_seen_at) VALUES(?,?,?)
            ON CONFLICT(company, external_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
        """, values)
        self.db.commit()

    def full_scan_due(self, company: str, interval_hours: int = 24) -> bool:
        row = self.db.execute("SELECT last_full_scan_at FROM source_state WHERE company=?", (company,)).fetchone()
        if row is None:
            return True
        last = datetime.fromisoformat(row[0])
        return datetime.now(timezone.utc) - last >= timedelta(hours=interval_hours)

    def mark_full_scan(self, company: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("""
            INSERT INTO source_state(company, last_full_scan_at) VALUES(?,?)
            ON CONFLICT(company) DO UPDATE SET last_full_scan_at=excluded.last_full_scan_at
        """, (company, now))
        self.db.commit()

    def scan_finish(self, run_id: int, status: str, count: int = 0, error: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("UPDATE scan_runs SET finished_at=?,status=?,found_count=?,error=? WHERE id=?",
                        (now, status, count, error, run_id))
        self.db.commit()
