"""
"Catch me up": summarise unread chat messages with checkable citations.

Every claim in the summary must cite the ids of the messages it came from.
Citations are verified deterministically against the input set (invented ids
are dropped and counted), and any link the model emits that wasn't in the
messages is stripped.
"""
from pydantic import BaseModel, Field

from .. import metrics
from ..gateway import Gateway
from ..guardrails import UNTRUSTED_NOTICE, clean_text, strip_foreign_urls, untrusted

MAX_MESSAGES = 300
MAX_MESSAGE_CHARS = 2000


class ChatMessage(BaseModel):
    id: int
    sender: str = Field(max_length=150)
    text: str = Field(max_length=10_000)
    sent_at: str = Field(max_length=40)


class CatchUpRequest(BaseModel):
    room_name: str = Field(default='', max_length=255)
    viewer: str = Field(max_length=150)
    messages: list[ChatMessage] = Field(max_length=MAX_MESSAGES)


class Cited(BaseModel):
    text: str = Field(max_length=400)
    message_ids: list[int] = Field(max_length=20)


class Topic(BaseModel):
    title: str = Field(max_length=80)
    summary: str = Field(max_length=500)
    message_ids: list[int] = Field(max_length=30)


class CatchUpSummary(BaseModel):
    tldr: str = Field(max_length=400, description='One or two sentences.')
    topics: list[Topic] = Field(max_length=5)
    decisions: list[Cited] = Field(max_length=8, description='Plans or decisions the group agreed on.')
    questions_for_you: list[Cited] = Field(max_length=8, description='Questions or requests aimed at the viewer.')


class CatchUpResult(BaseModel):
    summary: CatchUpSummary
    model: str
    cost_usd: float
    cited_ids_dropped: int


SYSTEM = f"""You summarise unread messages in a group chat for one member (the viewer).
{UNTRUSTED_NOTICE}

Rules:
- Be brief and concrete. Use the participants' names.
- Every topic, decision and question must cite the ids of the messages it is based on.
- Only include "questions_for_you" when a message asks the viewer something or mentions them.
- Never invent details, links or phone numbers that aren't in the messages.
- If there is little to report, say so in the tl;dr and leave the lists short or empty."""


def _render(req: CatchUpRequest) -> str:
    lines = [f'Viewer: {clean_text(req.viewer, 150)}', f'Chat: {clean_text(req.room_name, 255) or "direct message"}', '']
    for m in req.messages:
        lines.append(untrusted(m.text, MAX_MESSAGE_CHARS, id=m.id, sender=m.sender, at=m.sent_at))
    return '\n'.join(lines)


def _verify(summary: CatchUpSummary, valid_ids: set[int], sources: str) -> int:
    dropped = 0

    def keep(ids: list[int]) -> list[int]:
        nonlocal dropped
        good = [i for i in dict.fromkeys(ids) if i in valid_ids]
        dropped += len(ids) - len(good)
        metrics.ATTRIBUTION.labels('true').inc(len(good))
        metrics.ATTRIBUTION.labels('false').inc(len(ids) - len(good))
        return good

    summary.tldr = strip_foreign_urls(summary.tldr, sources)
    for t in summary.topics:
        t.message_ids = keep(t.message_ids)
        t.summary = strip_foreign_urls(t.summary, sources)
    for group in (summary.decisions, summary.questions_for_you):
        for c in group:
            c.message_ids = keep(c.message_ids)
            c.text = strip_foreign_urls(c.text, sources)
    # Claims left with no valid citation are unsupported: drop them.
    summary.topics = [t for t in summary.topics if t.message_ids]
    summary.decisions = [c for c in summary.decisions if c.message_ids]
    summary.questions_for_you = [c for c in summary.questions_for_you if c.message_ids]
    return dropped


async def catch_up(req: CatchUpRequest, gateway: Gateway, user_id: int) -> CatchUpResult:
    if not req.messages:
        return CatchUpResult(summary=CatchUpSummary(tldr="You're all caught up.", topics=[], decisions=[],
                                                    questions_for_you=[]), model='none', cost_usd=0.0,
                             cited_ids_dropped=0)
    rendered = _render(req)
    res = await gateway.structured('catchup.summarise', system=SYSTEM, user=rendered,
                                   schema=CatchUpSummary, user_id=user_id)
    sources = '\n'.join(m.text for m in req.messages)
    dropped = _verify(res.output, {m.id for m in req.messages}, sources)
    return CatchUpResult(summary=res.output, model=res.model, cost_usd=round(res.cost_usd, 6),
                         cited_ids_dropped=dropped)
