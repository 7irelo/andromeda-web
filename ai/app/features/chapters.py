"""
Video chapters from a timed transcript.

The model proposes chapter starts and titles; the output is then checked
deterministically: every start must fall inside the video, starts must
strictly increase with a minimum gap, the first chapter is pinned to 0:00,
titles are cleaned (no links, markup or control characters) and capped, and
at most MAX_CHAPTERS survive. Anything that fails a check is dropped, and a
single surviving chapter is no chapters at all.
"""
import re

from pydantic import BaseModel, Field

from ..gateway import Gateway
from ..guardrails import UNTRUSTED_NOTICE, clean_text, untrusted

MAX_UTTERANCES = 1500
MAX_UTTERANCE_CHARS = 500
MAX_TRANSCRIPT_CHARS = 60_000
MAX_CHAPTERS = 12
MAX_TITLE_CHARS = 80
MIN_GAP_S = 10.0
MIN_DURATION_S = 60.0

_URL_RE = re.compile(r'(https?://|www\.)\S+', re.IGNORECASE)


class TimedUtterance(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=2000)


class ChaptersRequest(BaseModel):
    title: str = Field(default='', max_length=255)
    duration_s: float = Field(gt=0, le=6 * 3600)
    utterances: list[TimedUtterance] = Field(max_length=MAX_UTTERANCES)


class Chapter(BaseModel):
    start_s: float
    title: str = Field(max_length=200)


class ChapterPlan(BaseModel):
    chapters: list[Chapter] = Field(max_length=30, description='In order. The first starts at 0.')


class ChaptersResult(BaseModel):
    chapters: list[Chapter]
    model: str
    cost_usd: float
    dropped: int


SYSTEM = f"""You split a video into chapters from its timestamped transcript.
{UNTRUSTED_NOTICE}

Rules:
- Return between 2 and {MAX_CHAPTERS} chapters in time order. The first starts at 0.
- Start each chapter where the speaker moves to a new topic, using the timestamps given (seconds).
- Chapters should be at least 30 seconds long; fewer, meaningful chapters beat many small ones.
- Titles are short (2 to 6 words), descriptive and in the language of the transcript.
- No links, emoji, quotes or numbering in titles. Never invent topics that aren't in the transcript.
- If the video has no clear structure, return an empty list."""


def _clock(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f'{m}:{s:02d}'


def _render(req: ChaptersRequest) -> str:
    lines, total = [], 0
    for u in req.utterances:
        line = f'[{u.start:.1f}s {_clock(u.start)}] {clean_text(u.text, MAX_UTTERANCE_CHARS).strip()}'
        total += len(line) + 1
        if total > MAX_TRANSCRIPT_CHARS:
            break
        lines.append(line)
    return '\n'.join([
        f'Duration: {req.duration_s:.0f} seconds',
        'Title:', untrusted(req.title, 255, kind='title'),
        'Transcript:', untrusted('\n'.join(lines), MAX_TRANSCRIPT_CHARS, kind='transcript'),
    ])


def clean_title(text: str) -> str:
    text = _URL_RE.sub('', clean_text(text, 1000))
    text = re.sub(r'[<>"`*_#\[\]]', '', text)
    text = ' '.join(text.split()).strip(' -:|.,;')
    return text[:MAX_TITLE_CHARS].rstrip()


def verify(chapters: list[Chapter], duration: float) -> tuple[list[Chapter], int]:
    kept: list[Chapter] = []
    for c in chapters:
        title = clean_title(c.title)
        start = c.start_s
        if not title or not (0 <= start <= duration) or start != start:  # NaN never equals itself
            continue
        if kept and start < kept[-1].start_s + MIN_GAP_S:
            continue
        kept.append(Chapter(start_s=round(start, 1), title=title))
        if len(kept) == MAX_CHAPTERS:
            break
    if len(kept) < 2:
        return [], len(chapters)
    kept[0].start_s = 0.0
    return kept, len(chapters) - len(kept)


async def chapters(req: ChaptersRequest, gateway: Gateway, user_id: int) -> ChaptersResult:
    if req.duration_s < MIN_DURATION_S or not any(u.text.strip() for u in req.utterances):
        return ChaptersResult(chapters=[], model='none', cost_usd=0.0, dropped=0)
    res = await gateway.structured('video.chapters', system=SYSTEM, user=_render(req), schema=ChapterPlan,
                                   user_id=user_id)
    kept, dropped = verify(res.output.chapters, req.duration_s)
    return ChaptersResult(chapters=kept, model=res.model, cost_usd=round(res.cost_usd, 6), dropped=dropped)
