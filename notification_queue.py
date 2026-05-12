"""Sanitized Telegram Bot API notification helper for job leads."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import requests

DB_PATH = Path(os.environ.get("JOB_HUNTER_QUEUE", "./runtime/jobs_queue.json"))


def load_queue() -> dict[str, dict[str, Any]]:
    if not DB_PATH.exists():
        return {}
    try:
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_queue(data: dict[str, dict[str, Any]]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_reply_draft(text: str) -> str:
    markers = ["FULL_REPLY_TEXT:", "DRAFT_REPLY:", "ПОЛНЫЙ ТЕКСТ МОЕГО ОТКЛИКА:", "ЧЕРНОВИК ОТКЛИКА:"]
    for marker in markers:
        if marker in text:
            return text.split(marker, 1)[-1].strip()
    return text.strip()


def save_job(target: str, summary: str, text: str) -> str:
    job_id = str(uuid.uuid4())[:8]
    data = load_queue()
    data[job_id] = {
        "target": target,
        "summary": summary,
        "text": clean_reply_draft(text),
    }
    save_queue(data)
    return job_id


def send_notification(token: str, chat_id: str, target: str, summary: str, text: str) -> None:
    job_id = save_job(target, summary, text)
    cleaned_text = load_queue()[job_id]["text"]

    message_text = (
        f"Target: {target}\n\n"
        f"Summary:\n{summary}\n\n"
        f"Draft reply:\n{cleaned_text}"
    )
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"send_{job_id}"},
                    {"text": "Edit", "callback_data": f"edit_{job_id}"},
                    {"text": "Skip", "callback_data": f"skip_{job_id}"},
                ]
            ]
        },
    }

    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20)
    response.raise_for_status()
