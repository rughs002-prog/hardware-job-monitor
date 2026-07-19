from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .adapters import ADAPTERS
from .matching import is_relevant, tag_job
from .notifier import render_digest, send_email
from .storage import Store


def load_dotenv(path: str = ".env") -> None:
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip().lstrip("\ufeff"), value.strip())


def scan(store: Store, config_path: str) -> int:
    companies = json.loads(Path(config_path).read_text(encoding="utf-8"))["companies"]
    new_count = 0
    for company in companies:
        if not company.get("enabled", False):
            continue
        run_id = store.scan_start(company["name"])
        try:
            company = dict(company)
            known_ids = store.source_ids(company["name"])
            full_scan = not known_ids or store.full_scan_due(company["name"])
            company["_known_external_ids"] = known_ids
            company["_incremental"] = not full_scan
            adapter = ADAPTERS[company["source"]["type"]]()
            jobs = [tag_job(job) for job in adapter.fetch(company)]
            store.remember_source_items(company["name"], jobs)
            if full_scan:
                store.mark_full_scan(company["name"])
            relevant = [job for job in jobs if is_relevant(job)]
            new_count += sum(store.upsert(job) for job in relevant)
            store.scan_finish(run_id, "ok", len(relevant))
            mode = "full" if full_scan else "incremental"
            print(f"OK  {company['name']}: {len(relevant)} relevant of {len(jobs)} fetched ({mode})")
        except Exception as exc:  # isolate source failures
            store.scan_finish(run_id, "error", error=str(exc))
            print(f"ERR {company['name']}: {exc}")
    return new_count


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Monitor official career sources for Israel hardware jobs")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan")
    sub.add_parser("preview-email")
    sub.add_parser("send-email")
    sub.add_parser("run", help="scan and then email all jobs not previously notified")
    args = parser.parse_args()
    with Store(os.getenv("JOB_DB_PATH", "data/jobs.db")) as store:
        if args.command == "scan":
            count = scan(store, os.getenv("COMPANIES_FILE", "config/companies.json"))
            print(f"New jobs stored: {count}")
        elif args.command == "preview-email":
            subject, body = render_digest(store.pending())
            print(subject + "\n" + body)
        elif args.command == "send-email":
            rows = store.pending()
            send_email(rows)
            store.mark_notified([row["fingerprint"] for row in rows])
            print(f"Sent {len(rows)} jobs")
        else:
            count = scan(store, os.getenv("COMPANIES_FILE", "config/companies.json"))
            print(f"New jobs stored: {count}")
            rows = store.pending()
            if rows:
                send_email(rows)
                store.mark_notified([row["fingerprint"] for row in rows])
            print(f"Sent {len(rows)} jobs")


if __name__ == "__main__":
    main()
