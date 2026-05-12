"""Sanitized Telegram job hunter daemon.

The private version uses a local Pyrogram user session and a Telegram Bot API
controller bot. This public version keeps the control flow and removes real
chat names, chat IDs, token paths, prompt details, and private buffers.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Protocol

from notification_queue import send_notification


@dataclass(frozen=True)
class Message:
    id: int
    text: str | None = None
    caption: str | None = None


class TelegramSearchClient(Protocol):
    async def search_messages(self, chat: str, query: str, limit: int) -> AsyncIterator[Message]:
        ...


class ClientFactory(Protocol):
    def __call__(self) -> TelegramSearchClient:
        ...


TARGET_CHATS = ["ai_jobs_source", "automation_jobs_source"]
CHECK_INTERVAL_SECONDS = 15 * 60
STATE_FILE = Path(os.environ.get("JOB_HUNTER_STATE", "./runtime/jobs_state.json"))
BUFFER_FILE = Path(os.environ.get("JOB_HUNTER_BUFFER", "./runtime/new_jobs_buffer.jsonl"))


def log(message: str) -> None:
    print(message)
    sys.stdout.flush()


def load_state() -> dict[str, int]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {chat: 0 for chat in TARGET_CHATS}


def save_state(state: dict[str, int]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def check_jobs(client_factory: ClientFactory) -> bool:
    state = load_state()
    new_messages_found = False
    client = client_factory()

    BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with BUFFER_FILE.open("w", encoding="utf-8") as buffer_file:
        for chat in TARGET_CHATS:
            log(f"Searching {chat}")
            last_id = state.get(chat, 0)
            highest_id = last_id

            async for message in client.search_messages(chat, query="#ищу", limit=15):
                if message.id <= last_id:
                    continue

                text = message.text or message.caption
                if text:
                    buffer_file.write(
                        json.dumps(
                            {"chat": chat, "id": message.id, "text": text},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    new_messages_found = True

                highest_id = max(highest_id, message.id)

            state[chat] = highest_id
            log(f"Finished {chat}")

    save_state(state)
    return new_messages_found


def run_llm_analysis(buffer_file: Path) -> list[dict[str, str]]:
    prompt = (
        "Analyze job posts from this JSONL file and return a strict JSON array "
        "with target, summary, and draft fields: "
        f"{buffer_file}"
    )
    env = os.environ.copy()
    result = subprocess.run(["gemini", "-p", prompt], env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("LLM analysis failed")

    output = result.stdout.strip()
    if "```json" in output:
        output = output.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in output:
        output = output.split("```", 1)[1].split("```", 1)[0].strip()

    parsed = json.loads(output)
    if isinstance(parsed, dict) and "response" in parsed:
        parsed = json.loads(str(parsed["response"]))
    if not isinstance(parsed, list):
        raise ValueError("LLM output must be a JSON array")
    return parsed


async def run_forever(client_factory: ClientFactory) -> None:
    bot_token = os.environ["JOB_HUNTER_BOT_TOKEN"]
    operator_chat_id = os.environ["JOB_HUNTER_OPERATOR_CHAT_ID"]

    log("Starting job hunter daemon")
    while True:
        has_new = await check_jobs(client_factory)
        if has_new:
            log("New jobs found; running analysis")
            for job in run_llm_analysis(BUFFER_FILE):
                target = job.get("target", "")
                summary = job.get("summary", "")
                draft = job.get("draft", "")
                if target and draft:
                    send_notification(bot_token, operator_chat_id, target, summary, draft)
        else:
            log("No new jobs this cycle")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
