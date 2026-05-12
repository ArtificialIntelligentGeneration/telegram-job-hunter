# Telegram Job Hunter Bot Showcase

This is a sanitized public version of a local Telegram job-hunting assistant. The private version watches selected Telegram sources, pulls new vacancy posts, asks an LLM to rank and draft replies, then sends an operator notification with approve/edit/skip actions.

## Flow

```text
Pyrogram user session
  -> source chats search
  -> JSONL buffer of new posts
  -> LLM analysis / scoring
  -> Telegram Bot API notification
  -> operator approve/edit/skip
```

## Included Files

- [`job_hunter_daemon.py`](./job_hunter_daemon.py) - async polling loop, state tracking, LLM handoff, and notification routing.
- [`notification_queue.py`](./notification_queue.py) - Bot API notification payload with inline review actions and local queue persistence.
- [`session_lock.py`](./session_lock.py) - file lock helper that prevents concurrent MTProto session access.

## Sanitization

Removed from the public version:

- real chat IDs and source chat names;
- `.env` paths and bot tokens;
- Pyrogram `.session` files;
- client/job buffers and generated drafts;
- personal reply templates and private lead data.
