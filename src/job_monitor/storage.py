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


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 fingerprint TEXT PRIMARY KEY, company TEXT NOT NULL, external_id TEXT, title TEXT NOT NULL,
 url TEXT NOT NULL, location TEXT, description TEXT, posted_at TEXT, source TEXT,
 tags_json TEXT NOT NULL, relevance_json TEXT NOT NULL, first_seen_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL, notified_at TEXT
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

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def upsert(self, job: Job) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.db.execute("SELECT 1 FROM jobs WHERE fingerprint=?", (job.fingerprint,)).fetchone()
        self.db.execute("""INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
            ON CONFLICT(fingerprint) DO UPDATE SET title=excluded.title, url=excluded.url,
            location=excluded.location, description=excluded.description, posted_at=excluded.posted_at,
            tags_json=excluded.tags_json, relevance_json=excluded.relevance_json,
            last_seen_at=excluded.last_seen_at""",
            (job.fingerprint, job.company, job.external_id, job.title, job.url, job.location,
             job.description, job.posted_at, job.source, json.dumps(job.tags), json.dumps(job.relevance), now, now))
        self.db.commit()
        return existing is None

    def pending(self) -> list[sqlite3.Row]:
        rows = self.db.execute("""
            SELECT * FROM jobs
            WHERE notified_at IS NULL
              AND (tags_json LIKE '%"student"%' OR tags_json LIKE '%"intern"%')
            ORDER BY first_seen_at
        """)
        pending, seen = [], set()
        for row in rows:
            title = row["title"].lower()
            tags = set(json.loads(row["tags_json"]))
            if any(term in title for term in SOFTWARE_TITLE_TERMS):
                continue
            if not ALERT_ROLE_TAGS.intersection(tags):
                continue
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
