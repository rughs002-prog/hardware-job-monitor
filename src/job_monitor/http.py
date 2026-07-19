from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def request_json(url: str, *, payload: dict[str, Any] | None = None, timeout: int | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": os.getenv("USER_AGENT", "HardwareJobMonitor/0.1"),
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(request, timeout=timeout or int(os.getenv("HTTP_TIMEOUT_SECONDS", "25"))) as response:
        return json.load(response)


def request_text(url: str, *, timeout: int | None = None) -> str:
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": os.getenv("USER_AGENT", "HardwareJobMonitor/0.1"),
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout or int(os.getenv("HTTP_TIMEOUT_SECONDS", "25"))) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
