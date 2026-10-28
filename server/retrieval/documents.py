"""
Turn content into the text that gets embedded and shown to the answer model.

Content whose author opted out of AI features is never indexed, so it can't
reach the embedding or answer models.

Chunking follows the content's structure: a post plus its top comments is one
document; listings are title, category, condition and description; long
descriptions split on paragraph boundaries.
"""
from dataclasses import dataclass

CHUNK_CHARS = 1800
MAX_CHUNKS = 8


@dataclass
class Document:
    kind: str
    id: int
    title: str
    author: str
    created_at: str
    text: str


def _chunks(text):
    text = (text or '').strip()
    if len(text) <= CHUNK_CHARS:
        return [text] if text else []
    out, cur = [], ''
    for para in text.split('\n'):
        while len(para) > CHUNK_CHARS:
            if cur:
                out.append(cur)
                cur = ''
            out.append(para[:CHUNK_CHARS])
            para = para[CHUNK_CHARS:]
        if len(cur) + len(para) + 1 > CHUNK_CHARS:
            out.append(cur)
            cur = para
        else:
            cur = f'{cur}\n{para}' if cur else para
    if cur:
        out.append(cur)
    return [c for c in out if c.strip()][:MAX_CHUNKS]


def load(kind, object_id):
    """The current document for an object, or None if it's gone or shouldn't be indexed."""
    if kind == 'posts':
        from posts.models import Post
        p = Post.objects.select_related('author', 'group', 'page').filter(pk=object_id).first()
        if p is None or p.moderation_status == 'removed' or p.author.ai_opt_out:
            return None
        comments = p.comments.filter(parent__isnull=True).exclude(moderation_status='removed') \
            .select_related('author').order_by('-created_at')[:3]
        where = f' in {p.group.name}' if p.group_id else (f' on {p.page.name}' if p.page_id else '')
        parts = [f'Post by {p.author.get_full_name() or p.author.username}{where}:', p.content]
        if p.link_title:
            parts.append(f'Link: {p.link_title}. {p.link_description}')
        tags = list(p.tags.values_list('name', flat=True)[:10])
        if tags:
            parts.append(' '.join(f'#{t}' for t in tags))
        for c in comments:
            parts.append(f'Comment from {c.author.username}: {c.content}')
        title = (p.content or p.link_title or '').strip().split('\n')[0][:120]
        return Document('posts', p.id, title, p.author.username, p.created_at.isoformat(), '\n'.join(parts))
    if kind == 'listings':
        from marketplace.models import Listing
        x = Listing.objects.select_related('seller', 'category').filter(pk=object_id).first()
        if x is None or x.moderation_status == 'removed' or x.seller.ai_opt_out:
            return None
        cat = x.category.name if x.category_id else 'Uncategorised'
        text = (f'Listing for sale: {x.title}\nCategory: {cat}. Condition: {x.get_condition_display()}. '
                f'Price: {x.currency} {x.price}. Location: {x.location or "not given"}.\n{x.description}')
        return Document('listings', x.id, x.title, x.seller.username, x.created_at.isoformat(), text)
    if kind == 'groups':
        from groups.models import Group
        g = Group.objects.filter(pk=object_id).first()
        if g is None:
            return None
        return Document('groups', g.id, g.name, '', g.created_at.isoformat(),
                        f'Group: {g.name}\n{g.description}')
    if kind == 'pages':
        from pages.models import Page
        pg = Page.objects.filter(pk=object_id).first()
        if pg is None:
            return None
        return Document('pages', pg.id, pg.name, '', pg.created_at.isoformat(),
                        f'Page: {pg.name} ({pg.category})\n{pg.description}')
    if kind == 'videos':
        from watch.models import Video
        v = Video.objects.select_related('uploader').filter(pk=object_id).first()
        if v is None or v.uploader.ai_opt_out:
            return None
        transcript = getattr(v, 'transcript', '') or ''
        text = f'Video: {v.title}\n{v.description}' + (f'\nTranscript: {transcript}' if transcript else '')
        return Document('videos', v.id, v.title, v.uploader.username, v.created_at.isoformat(), text)
    raise ValueError(kind)


def chunks(doc):
    return _chunks(doc.text)
