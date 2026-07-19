from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from sqlite3 import Row


def render_digest(rows: list[Row]) -> tuple[str, str]:
    subject = f"{len(rows)} new Israel hardware student/intern job{'s' if len(rows) != 1 else ''}"
    items = []
    for row in rows:
        tags = ", ".join(__import__("json").loads(row["tags_json"]))
        items.append(f'<li><b>{html.escape(row["company"])} — {html.escape(row["title"])}</b><br>'
                     f'{html.escape(row["location"] or "Location not stated")} · {html.escape(tags)}<br>'
                     f'<a href="{html.escape(row["url"], quote=True)}">Official job posting</a></li>')
    return subject, "<h2>New hardware / VLSI student and intern roles</h2><ul>" + "\n".join(items) + "</ul>"


def send_email(rows: list[Row]) -> None:
    if not rows:
        return
    required = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing email settings: " + ", ".join(missing))
    subject, body = render_digest(rows)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, os.environ["EMAIL_FROM"], os.environ["EMAIL_TO"]
    msg.set_content("Your email client must support HTML to display this digest.")
    msg.add_alternative(body, subtype="html")
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30) as smtp:
        if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
