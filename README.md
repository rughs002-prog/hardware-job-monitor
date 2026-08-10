# Hardware / VLSI Student Job Monitor — MVP

This project monitors **official company career sources** for Israel-based hardware and electrical-engineering jobs. It intentionally casts a wide net: a role is kept when it is located in Israel and has a hardware-related tag. Seniority, missing skills, degree year, and prior experience do **not** automatically exclude it.

## What is implemented

- Official ATS adapters for Greenhouse, Lever, SmartRecruiters, and Workday, plus a conservative official-HTML adapter.
- A 27-company Israel hardware catalog with 14 live-tested official sources.
- Broad role tags: chip/ASIC/SoC, physical design, RTL/digital design, verification, validation, FPGA, firmware, embedded, analog/mixed-signal/RF, DFT, CAD/EDA, and board hardware.
- Level tags: Student, Intern/Internship/Co-op, Working Student, Junior, Entry Level, Graduate, and University variants.
- Conservative Israel-location matching.
- SQLite history, stable deduplication, first/last-seen timestamps, and scan audit records.
- Incremental Workday scans remember every source posting and stop after three fully-known pages. A full safety scan runs once every 24 hours.
- Email alerts are restricted to Student and Intern/Internship/Co-op roles. Other hardware jobs may be retained in history but are never included in notifications.
- HTML email digest preview and SMTP delivery.
- Source isolation: one broken company endpoint does not stop the rest of the scan.
- Light CV-context tags for digital foundations, C/firmware, and VLSI direction. These are informational only.

## Architecture

```text
Official ATS/API -> source adapter -> normalize Job -> Israel + broad hardware tags
       -> SQLite upsert/deduplicate -> pending new jobs -> email digest
```

The catalog is deliberately honest about coverage. `enabled: true` means the official source was verified. Sources that block automation or do not expose a stable listing remain disabled instead of being reported as covered.

## Quick start (Windows PowerShell)

Python 3.11 or newer is required. No third-party runtime package is needed.

```powershell
cd outputs/hardware-job-monitor
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
job-monitor scan
job-monitor preview-email
```

The first scan creates `data/jobs.db` and records every source posting. Later scans use that history to stop early; once every 24 hours the monitor performs a complete safety scan.

## Email credentials (provide later)

Edit `.env` only when ready to send mail:

- `SMTP_HOST` and `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD` — for Gmail, use an **App Password**, not the normal account password
- `EMAIL_FROM` and `EMAIL_TO`

Then run:

```powershell
job-monitor send-email
```

On Windows, the safer setup path is to run `scripts/configure-gmail.ps1`. It prompts for the Gmail App Password without displaying it and saves it only in the ignored local `.env` file.

Jobs are marked as notified only after SMTP delivery succeeds. `.env` is ignored by Git.

For the normal automated cycle, use `job-monitor run`. It scans every enabled source and then emails every job that has not previously been notified.

## Scheduling

For local operation, after completing `.env` and successfully sending a test email, install the included Windows task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-scheduled-task.ps1
```

It runs `scripts/run-monitor.ps1` every six hours and writes results to `logs/monitor.log`. For cloud deployment, the same `job-monitor run` command can run in a scheduled container or CI job; secrets must be stored in the platform's secret manager. No deployment credentials are needed yet.

For always-on operation while the computer is off, the project includes `.github/workflows/job-monitor.yml`. Follow [CLOUD_SETUP.md](CLOUD_SETUP.md) to deploy it to a private GitHub repository, test the cloud run, and then disable the local Windows task.

## Add or activate a company

Edit `config/companies.json`. Prefer, in order:

1. Public official ATS API (Greenhouse, Lever, SmartRecruiters).
2. The company's official Workday JSON search endpoint.
3. A company-specific adapter with fixtures and a test.

Never enable a guessed board token or silently fall back to LinkedIn. A new source should first be tested with `job-monitor scan`; its failure will be recorded in `scan_runs`.

Example Greenhouse entry:

```json
{"name":"Example","enabled":true,"source":{"type":"greenhouse","board_token":"example"}}
```

## Known MVP limitations and next steps

- ATS endpoints can change. NVIDIA was live-tested on 2026-07-19; source failures are recorded and isolated.
- Workday summary results sometimes omit the full description. Location and title are enough for broad discovery, but a later version should fetch each detail page before enriching tags.
- Company-specific connectors are still needed for Apple, Amazon, Google, Intel, Microsoft, Mobileye, and other proprietary career sites.
- An operational deployment should add retries/backoff, structured logs, a health alert for repeatedly failing sources, and retention/closure tracking.
- After one week of observed results, tune location aliases and tags based on false positives—without narrowing the search aggressively.

## Test

If `pytest` is installed:

```powershell
python -m pytest
```

Or run the standard-library smoke check used during development:

```powershell
python -m compileall -q src tests
```
# Run intelligence and job lifecycle

Every run now prints a per-company table and writes it to the GitHub Actions run
summary. It reports fetched, relevant, ignored, high-priority, broader related,
new, modified, closed, sent, and failed counts. Inclusion and exclusion reason
counts are printed below each company.

`incremental-partial` is important: Workday sources stop after consecutive pages
whose IDs are already known. A zero in such a run does **not** mean that Marvell,
Cadence, Broadcom, Analog Devices, NXP, or another company has no Israel roles.
A complete scan is forced every six hours by default. Closed-job detection only
runs on complete listings, so a partial scan cannot falsely close jobs.

Categories are RTL, Physical Design, Formal Verification, Design Verification,
Validation, FPGA, Embedded, Firmware, Board/Hardware, Analog/Mixed-Signal, RF,
Signal Processing, CAD/EDA, Power, Integration, Mechanical, and Software-other.

Discovery remains broad:

- `high` means a Central Israel Student, Intern, or Junior title in a target
  category and is eligible for immediate email. Central Israel includes the Tel
  Aviv metro, Herzliya/Ra'anana/Kfar Saba, Petah Tikva/Rosh HaAyin, Netanya,
  Rehovot, Modi'in, Airport City, Yehud and Lod.
- `related` is stored and tracked but does not generate an immediate email.
- `excluded` is counted with reasons but is not stored as a relevant job.

Existing SQLite databases are migrated in place. New, modified, and closed states
use a stable company/external-ID fingerprint plus a content hash. Modified jobs
are tracked in summaries; email remains focused on unseen high-priority jobs.
