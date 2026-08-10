from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from .adapters import ADAPTERS
from .matching import is_relevant, reason_counts, tag_job
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


def _empty_summary(company: str) -> dict:
    return {
        "company": company, "mode": "", "fetched": 0, "relevant": 0, "ignored": 0,
        "high_priority": 0, "related": 0, "new": 0, "modified": 0, "closed": 0,
        "sent": 0, "failures": 0, "inclusion_reasons": {}, "exclusion_reasons": {},
    }


def print_summary(summaries: list[dict], sent: int = 0) -> None:
    print("\nRUN SUMMARY")
    print("Company | Mode | Fetched | Relevant | Ignored | High | Related | New | Modified | Closed | Sent | Failures")
    for item in summaries:
        print(
            f"{item['company']} | {item['mode']} | {item['fetched']} | {item['relevant']} | "
            f"{item['ignored']} | {item['high_priority']} | {item['related']} | {item['new']} | "
            f"{item['modified']} | {item['closed']} | {item['sent']} | {item['failures']}"
        )
        if item["inclusion_reasons"]:
            print("  included: " + ", ".join(f"{k}={v}" for k, v in item["inclusion_reasons"].items()))
        if item["exclusion_reasons"]:
            print("  ignored: " + ", ".join(f"{k}={v}" for k, v in item["exclusion_reasons"].items()))
    totals = Counter()
    for item in summaries:
        for key in ("fetched", "relevant", "ignored", "high_priority", "related",
                    "new", "modified", "closed", "failures"):
            totals[key] += item[key]
    print(
        "TOTAL | fetched={fetched} relevant={relevant} ignored={ignored} high={high_priority} "
        "related={related} new={new} modified={modified} closed={closed} sent={sent} failures={failures}"
        .format(sent=sent, **totals)
    )
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        lines = [
            "## Hardware job monitor summary", "",
            "| Company | Mode | Fetched | Relevant | Ignored | High | Related | New | Modified | Closed | Sent | Failures |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in summaries:
            lines.append(
                f"| {item['company']} | {item['mode']} | {item['fetched']} | {item['relevant']} | "
                f"{item['ignored']} | {item['high_priority']} | {item['related']} | {item['new']} | "
                f"{item['modified']} | {item['closed']} | {item['sent']} | {item['failures']} |"
            )
        lines += [
            "",
            f"**Overall:** fetched {totals['fetched']}, relevant {totals['relevant']}, "
            f"ignored {totals['ignored']}, new {totals['new']}, modified {totals['modified']}, "
            f"closed {totals['closed']}, sent {sent}, failures {totals['failures']}.",
            "",
            "_`incremental-partial` means a Workday scan stopped after consecutive known pages; "
            "zero relevant there does not prove that the company has no relevant jobs._",
        ]
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def scan(store: Store, config_path: str) -> list[dict]:
    companies = json.loads(Path(config_path).read_text(encoding="utf-8"))["companies"]
    summaries = []
    for configured in companies:
        if not configured.get("enabled", False):
            continue
        item = _empty_summary(configured["name"])
        summaries.append(item)
        run_id = store.scan_start(configured["name"])
        try:
            company = dict(configured)
            known_ids = store.source_ids(company["name"])
            full_scan = not known_ids or store.full_scan_due(
                company["name"], int(company["source"].get("full_scan_interval_hours", 6))
            )
            company["_known_external_ids"] = known_ids
            company["_incremental"] = not full_scan
            adapter = ADAPTERS[company["source"]["type"]]()
            jobs = [tag_job(job) for job in adapter.fetch(company)]
            store.remember_source_items(company["name"], jobs)
            if full_scan:
                store.mark_full_scan(company["name"])
            relevant = [job for job in jobs if is_relevant(job)]
            ignored = [job for job in jobs if not is_relevant(job)]
            statuses = Counter(store.upsert(job) for job in relevant)
            complete_listing = full_scan or company["source"]["type"] != "workday"
            closed = store.mark_closed_missing(
                company["name"], {job.fingerprint for job in relevant}
            ) if complete_listing else 0
            item.update({
                "mode": "full" if complete_listing else "incremental-partial",
                "fetched": len(jobs), "relevant": len(relevant), "ignored": len(ignored),
                "high_priority": sum(job.priority == "high" for job in relevant),
                "related": sum(job.priority == "related" for job in relevant),
                "new": statuses["new"], "modified": statuses["modified"], "closed": closed,
                "inclusion_reasons": reason_counts(relevant, True),
                "exclusion_reasons": reason_counts(ignored, False),
            })
            store.scan_finish(run_id, "ok", len(relevant))
            print(
                f"OK  {company['name']}: {len(relevant)} relevant ({item['high_priority']} high) "
                f"of {len(jobs)} fetched [{item['mode']}]"
            )
        except Exception as exc:
            item.update({"mode": "failed", "failures": 1})
            store.scan_finish(run_id, "error", error=str(exc))
            print(f"ERR {configured['name']}: {exc}")
    return summaries


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Monitor official career sources for Israel hardware jobs")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan")
    sub.add_parser("preview-email")
    sub.add_parser("send-email")
    sub.add_parser("run", help="scan and then email all high-priority jobs not previously notified")
    args = parser.parse_args()
    with Store(os.getenv("JOB_DB_PATH", "data/jobs.db")) as store:
        if args.command == "scan":
            print_summary(scan(store, os.getenv("COMPANIES_FILE", "config/companies.json")))
        elif args.command == "preview-email":
            subject, body = render_digest(store.pending())
            print(subject + "\n" + body)
        elif args.command == "send-email":
            rows = store.pending()
            send_email(rows)
            store.mark_notified([row["fingerprint"] for row in rows])
            print(f"Sent {len(rows)} jobs")
        else:
            summaries = scan(store, os.getenv("COMPANIES_FILE", "config/companies.json"))
            rows = store.pending()
            if rows:
                send_email(rows)
                store.mark_notified([row["fingerprint"] for row in rows])
            sent_by_company = Counter(row["company"] for row in rows)
            for item in summaries:
                item["sent"] = sent_by_company[item["company"]]
            print_summary(summaries, sent=len(rows))


if __name__ == "__main__":
    main()
