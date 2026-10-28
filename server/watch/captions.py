"""
Transcripts, captions and chapters from the AI service.

Everything the AI service returns is checked again here before it's stored:
captions must be WebVTT and bounded in size, and chapters must be ordered,
inside the video and short. The service verifies the same rules; this is
defence in depth for data that ends up in other people's browsers.
"""
import re

from core.ai_client import AIRejected, AIUnavailable

MAX_TRANSCRIPT_CHARS = 100_000
MAX_VTT_CHARS = 400_000
MAX_UTTERANCES = 1500
MAX_UTTERANCE_CHARS = 500
MAX_CHAPTERS = 12
MAX_CHAPTER_TITLE = 80
MIN_CHAPTER_GAP_S = 10
MIN_DURATION_FOR_CHAPTERS_S = 120

_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_URL_RE = re.compile(r'(https?://|www\.)\S+', re.IGNORECASE)


def is_transient(exc):
    """AI outages are worth a retry; refusals (too large, over budget, bad audio) are not."""
    return isinstance(exc, AIUnavailable) or (isinstance(exc, AIRejected) and exc.status == 503)


def clean_vtt(vtt):
    vtt = _CONTROL_RE.sub('', vtt or '') if isinstance(vtt, str) else ''
    if not vtt.startswith('WEBVTT') or len(vtt) > MAX_VTT_CHARS:
        return ''
    return vtt


def clean_transcript(text):
    return _CONTROL_RE.sub('', text if isinstance(text, str) else '').strip()[:MAX_TRANSCRIPT_CHARS]


def utterances_payload(utterances):
    out, total = [], 0
    for u in utterances if isinstance(utterances, list) else []:
        if not isinstance(u, dict):
            continue
        text = clean_transcript(u.get('text'))[:MAX_UTTERANCE_CHARS]
        try:
            start, end = float(u.get('start', 0)), float(u.get('end', 0))
        except (TypeError, ValueError):
            continue
        if not text or start < 0 or end < start:
            continue
        total += len(text)
        if len(out) >= MAX_UTTERANCES or total > 60_000:
            break
        out.append({'start': round(start, 2), 'end': round(end, 2), 'text': text})
    return out


def _title(text):
    text = _URL_RE.sub('', _CONTROL_RE.sub('', text if isinstance(text, str) else ''))
    text = ' '.join(text.replace('<', '').replace('>', '').split()).strip(' -:|')
    return text[:MAX_CHAPTER_TITLE].rstrip()


def clean_chapters(chapters, duration):
    """Keep chapters that start inside the video, in order, with a usable title."""
    kept = []
    for c in chapters if isinstance(chapters, list) else []:
        if not isinstance(c, dict):
            continue
        try:
            start = float(c.get('start_s'))
        except (TypeError, ValueError):
            continue
        title = _title(c.get('title'))
        if not title or not (0 <= start <= duration):
            continue
        if kept and start < kept[-1]['start_s'] + MIN_CHAPTER_GAP_S:
            continue
        kept.append({'start_s': round(start, 1), 'title': title})
        if len(kept) == MAX_CHAPTERS:
            break
    if len(kept) < 2:
        return []
    kept[0]['start_s'] = 0.0
    return kept
