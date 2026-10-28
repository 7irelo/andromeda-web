"""
Shared helpers for the smart-reply fine-tuning pipeline.

Prompts are rendered with the service's own system prompt and renderer
(``app.features.replies``), so the model is trained on exactly what it will
see when the gateway routes the ``lora`` variant to it.
"""
import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path

from app.features.replies import MAX_MESSAGES, MAX_SUGGESTION_CHARS, SYSTEM, RepliesRequest, _render
from app.guardrails import strip_foreign_contacts

# Signs that a row wasn't pseudonymised or came from somewhere it shouldn't have.
_UNSAFE_RE = re.compile(r'@[\w-]+\.[a-z]{2,}|example\.test|\bdemo\d+\b', re.IGNORECASE)


def read_jsonl(path: str | Path) -> Iterator[dict]:
    with open(path, encoding='utf-8') as fh:
        for n, line in enumerate(fh, start=1):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(f'{path}:{n}: invalid JSON ({exc})') from None


def write_jsonl(path: str | Path, rows) -> int:
    count = 0
    with open(path, 'w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
            count += 1
    return count


def check_conversation(conv: dict) -> None:
    """Refuse anything that doesn't look like a pseudonymised seed export."""
    for m in conv.get('messages', []):
        if not re.fullmatch(r'Person \d+', m.get('speaker', '')):
            raise SystemExit(f'conversation {conv.get("conversation")}: speaker {m.get("speaker")!r} is not a pseudonym')
        if _UNSAFE_RE.search(m.get('text', '')):
            raise SystemExit(f'conversation {conv.get("conversation")}: message {m.get("i")} looks un-pseudonymised')


def prompt_for(messages: list[dict], end: int, viewer: str) -> tuple[str, str]:
    """System and user prompt for the viewer replying after ``messages[:end]``."""
    context = messages[max(0, end - MAX_MESSAGES):end]
    req = RepliesRequest(viewer=viewer, messages=[
        {'id': m['i'], 'sender': m['speaker'], 'text': m['text'], 'is_viewer': m['speaker'] == viewer}
        for m in context
    ])
    return SYSTEM, _render(req)


def usable_reply(text: str) -> bool:
    """Short, and free of links or contact details (we never want to teach the model to write those)."""
    text = ' '.join((text or '').split())
    return 0 < len(text) <= MAX_SUGGESTION_CHARS and strip_foreign_contacts(text, '')[1] == 0


def target(suggestions: list[str]) -> str:
    return json.dumps({'suggestions': suggestions}, ensure_ascii=False)


def split_of(conversation_id, eval_fraction: float) -> str:
    """Deterministic train/eval split by conversation, so no conversation lands in both."""
    bucket = int(hashlib.sha256(str(conversation_id).encode()).hexdigest()[:8], 16) % 1000
    return 'eval' if bucket < eval_fraction * 1000 else 'train'
