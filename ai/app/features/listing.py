"""
Listing Assistant: photos in, an editable listing draft out.

The model looks at up to four photos (already validated and re-encoded by
Django) and an optional seller hint, and suggests a title, description,
category and condition. It never prices anything: Django derives the price
range from comparable listings.

Guardrails:
- the category is constrained to the real category slugs at the schema level,
  and checked again afterwards (a fallback provider may not enforce enums);
- the condition is constrained to the listing model's choices;
- the hint is untrusted user content;
- links, phone numbers and email addresses the model writes into the text are
  stripped unless the seller wrote them in the hint.
"""
import base64
import binascii
import re
from typing import Literal

from pydantic import BaseModel, Field, create_model, field_validator

from ..gateway import Gateway
from ..guardrails import UNTRUSTED_NOTICE, clean_text, strip_foreign_urls, untrusted

MAX_IMAGES = 4
MAX_IMAGE_B64 = 4 * 1024 * 1024   # per image, after Django downscales to 1568 px
MAX_CATEGORIES = 300
MAX_TITLE = 120
MAX_DESCRIPTION = 2000

Condition = Literal['new', 'like_new', 'good', 'fair', 'poor']

_PHONE_RE = re.compile(r'(?<![\w.])\+?\(?\d[\d\s().-]{6,18}\d(?![\w.])')
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')


class DraftImage(BaseModel):
    media_type: Literal['image/jpeg', 'image/png', 'image/webp', 'image/gif']
    data: str = Field(min_length=16, max_length=MAX_IMAGE_B64)

    @field_validator('data')
    @classmethod
    def _is_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError('Image data must be base64') from None
        return value


class CategoryOption(BaseModel):
    slug: str = Field(min_length=1, max_length=50, pattern=r'^[-a-zA-Z0-9_]+$')
    name: str = Field(min_length=1, max_length=210)


class DraftRequest(BaseModel):
    images: list[DraftImage] = Field(min_length=1, max_length=MAX_IMAGES)
    hint: str = Field(default='', max_length=500)
    categories: list[CategoryOption] = Field(default_factory=list, max_length=MAX_CATEGORIES)


class ListingDraft(BaseModel):
    title: str
    description: str
    category: str | None
    condition: Condition | None


class DraftResult(BaseModel):
    draft: ListingDraft
    model: str
    cost_usd: float
    removed_contacts: int


SYSTEM = f"""You help people sell second-hand items on a local marketplace. From the seller's photos,
and their note if there is one, draft the listing for them to review and edit.
{UNTRUSTED_NOTICE}

- "title": what the item is, in under 80 characters: brand, model and the key detail a buyer searches
  for ("Samsung Galaxy S21 128GB, Phantom Grey"). No hype, no emoji, no ALL CAPS.
- "description": 2 to 5 short sentences a buyer would find useful: what it is, visible condition,
  what's included, notable features. Only describe what you can see or the seller states. Do not
  invent specifications, history, defects or accessories you can't see.
- "category": the single best slug from the allowed list, or null if none fits.
- "condition": judge only from the photos and the note: new (sealed/unused), like_new, good,
  fair (visible wear), poor (damaged or for parts). Use null if you can't tell.
- Never mention or estimate a price, and never add links, phone numbers, emails or meeting places.
- If the photos don't show something that can be sold, give a short neutral title and description
  saying so, with category and condition null."""


def _schema(slugs: list[str]) -> type[BaseModel]:
    """The output model, with the category constrained to the slugs this request allows."""
    if slugs:
        category = (Literal[tuple(slugs)] | None, Field(description='One allowed category slug, or null.'))
    else:
        category = (None, Field(default=None, description='Always null: no categories are configured.'))
    return create_model(
        'ListingDraftOutput',
        title=(str, Field(description='Under 80 characters.')),
        description=(str, Field(description='2 to 5 short sentences.')),
        category=category,
        condition=(Condition | None, Field(description='Condition judged from the photos, or null.')),
    )


def _render(req: DraftRequest) -> list[dict]:
    allowed = '\n'.join(f'- {c.slug}: {clean_text(c.name, 210)}' for c in req.categories) or '(none)'
    note = untrusted(req.hint, 500, kind='seller_note') if req.hint.strip() else '(The seller added no note.)'
    parts: list[dict] = [{'type': 'image', 'media_type': img.media_type, 'data': img.data} for img in req.images]
    parts.append({'type': 'text', 'text': f'Allowed categories (slug: name):\n{allowed}\n\nSeller note:\n{note}\n\n'
                                          f'Draft the listing from the {len(req.images)} photo(s) above.'})
    return parts


def _strip_contacts(text: str, sources: str) -> tuple[str, int]:
    removed = 0

    def phone(m: re.Match) -> str:
        nonlocal removed
        digits = re.sub(r'\D', '', m.group(0))
        if not 9 <= len(digits) <= 15 or digits in re.sub(r'\D', '', sources):
            return m.group(0)
        removed += 1
        return '[number removed]'

    def email(m: re.Match) -> str:
        nonlocal removed
        if m.group(0) in sources:
            return m.group(0)
        removed += 1
        return '[email removed]'

    before = text.count('[link removed]')
    text = strip_foreign_urls(text, sources)
    removed += text.count('[link removed]') - before
    text = _EMAIL_RE.sub(email, text)
    text = _PHONE_RE.sub(phone, text)
    return text, removed


async def draft(req: DraftRequest, gateway: Gateway, user_id: int) -> DraftResult:
    slugs = list(dict.fromkeys(c.slug for c in req.categories))
    res = await gateway.structured('listing.draft', system=SYSTEM, user=_render(req), schema=_schema(slugs),
                                   user_id=user_id)
    out = res.output
    category = out.category
    condition = out.condition if out.condition in Condition.__args__ else None
    title, removed_title = _strip_contacts(clean_text(out.title, 500).strip(), req.hint)
    description, removed_desc = _strip_contacts(clean_text(out.description, 5000).strip(), req.hint)
    return DraftResult(
        draft=ListingDraft(
            title=' '.join(title.split())[:MAX_TITLE],
            description=description[:MAX_DESCRIPTION],
            # Defence in depth: only a slug from the request survives, whatever the provider returned.
            category=category if category in slugs else None,
            condition=condition,
        ),
        model=res.model, cost_usd=round(res.cost_usd, 6), removed_contacts=removed_title + removed_desc,
    )
