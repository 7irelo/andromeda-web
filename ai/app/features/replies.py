"""
Smart replies: three short replies the viewer could send next in a chat.

Latency matters more than depth here (the goal is < 400 ms p95), so the
prompt is short, the stable system prompt is cached, and outputs are small.
Django sends only the latest messages of the one room being viewed, with
blocked users' messages already removed.

Output is untrusted. Each suggestion is cleaned and checked deterministically:
- at most three, each at most 120 characters, no empties or duplicates;
- a suggestion carrying a link, phone number or email address that isn't in
  the chat is dropped (not patched: a reply with "[link removed]" is useless);
- anything that echoes the prompt's delimiters is dropped;
- when the moderation endpoint is configured, flagged suggestions are dropped,
  and if it can't be reached nothing is shown (fail closed).

The A/B variant arrives from Django and is checked against an allow-list; it
only selects which route is primary.
"""
import asyncio
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..gateway import Gateway
from ..guardrails import UNTRUSTED_NOTICE, clean_text, strip_foreign_contacts, untrusted

logger = logging.getLogger(__name__)

MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 500
MAX_SUGGESTIONS = 3
MAX_SUGGESTION_CHARS = 120

# Allow-list: variant -> gateway job. Anything else is rejected at validation.
Variant = Literal['haiku', 'luna', 'lora']
VARIANT_JOBS: dict[str, str] = {
    'haiku': 'replies.suggest',
    'luna': 'replies.suggest.luna',
    'lora': 'replies.suggest.lora',
}

_LEAK_RE = re.compile(r'untrusted|tag removed|\[(?:link|number|email) removed\]', re.IGNORECASE)


class ReplyMessage(BaseModel):
    id: int
    sender: str = Field(max_length=150)
    text: str = Field(max_length=MAX_MESSAGE_CHARS * 4)
    is_viewer: bool = False


class RepliesRequest(BaseModel):
    viewer: str = Field(max_length=150)
    messages: list[ReplyMessage] = Field(max_length=MAX_MESSAGES)
    variant: Variant = 'haiku'


class Suggestions(BaseModel):
    # Deliberately lenient: limits are enforced after parsing, so one long or extra item from
    # a model doesn't fail the whole call.
    suggestions: list[str] = Field(description='Three short, different replies the viewer could send.')


class RepliesResult(BaseModel):
    suggestions: list[str]
    model: str
    variant: str
    cost_usd: float
    dropped: int


SYSTEM = f"""You suggest three short replies the viewer could send next in a chat.
{UNTRUSTED_NOTICE}

- Write as the viewer, replying to the latest messages from the others, in the chat's language and tone.
- Each reply under 80 characters. Make the three meaningfully different (e.g. yes / no / a question).
- Never invent facts, plans, links, phone numbers, emails or addresses the chat doesn't contain.
- Never agree to send money or share personal details on the viewer's behalf.
- If nothing needs an answer, suggest brief, friendly acknowledgements."""


def _render(req: RepliesRequest) -> str:
    lines = [f'Viewer: {clean_text(req.viewer, 150)}', '']
    for m in req.messages:
        sender = 'viewer' if m.is_viewer else m.sender
        lines.append(untrusted(m.text, MAX_MESSAGE_CHARS, id=m.id, sender=sender))
    lines.append('\nSuggest three replies for the viewer.')
    return '\n'.join(lines)


def _clean(raw: list[str], sources: str) -> tuple[list[str], int]:
    kept: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = ' '.join(clean_text(str(item), 1000).split()).strip().strip('"“”').strip()
        if not text or len(text) > MAX_SUGGESTION_CHARS or _LEAK_RE.search(text):
            continue
        if strip_foreign_contacts(text, sources)[1]:
            continue
        key = text.casefold().rstrip('.!?')
        if key in seen:
            continue
        seen.add(key)
        kept.append(text)
        if len(kept) == MAX_SUGGESTIONS:
            break
    return kept, len(raw) - len(kept)


async def _moderated(suggestions: list[str], stage0) -> list[str]:
    """Drop flagged suggestions. With moderation configured but unreachable, show nothing."""
    if stage0 is None or not suggestions:
        return suggestions
    try:
        verdicts = await asyncio.gather(*(stage0.moderate(s) for s in suggestions))
    except Exception as exc:  # any failure, transient or not: fail closed
        logger.warning('Reply moderation unavailable, withholding suggestions: %s', exc)
        return []
    return [s for s, v in zip(suggestions, verdicts, strict=True) if not v.get('flagged')]


async def suggest(req: RepliesRequest, gateway: Gateway, user_id: int, stage0=None) -> RepliesResult:
    if not any(not m.is_viewer and m.text.strip() for m in req.messages):
        return RepliesResult(suggestions=[], model='none', variant=req.variant, cost_usd=0.0, dropped=0)
    res = await gateway.structured(VARIANT_JOBS[req.variant], system=SYSTEM, user=_render(req),
                                   schema=Suggestions, user_id=user_id)
    sources = '\n'.join(m.text for m in req.messages)
    kept, dropped = _clean(list(res.output.suggestions or []), sources)
    safe = await _moderated(kept, stage0)
    return RepliesResult(suggestions=safe, model=res.model, variant=req.variant, cost_usd=round(res.cost_usd, 6),
                         dropped=dropped + len(kept) - len(safe))
