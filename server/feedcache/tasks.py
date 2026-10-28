import logging
from types import SimpleNamespace

from celery import shared_task

from . import candidates

logger = logging.getLogger(__name__)


@shared_task(name='feedcache.tasks.fan_out_post', queue='default', ignore_result=True)
def fan_out_post(post_id):
    from posts.models import Post

    post = Post.objects.filter(pk=post_id).first()
    if post is not None:
        candidates.fan_out(post)


@shared_task(name='feedcache.tasks.refresh_post', queue='default', ignore_result=True)
def refresh_post(post_id):
    """The audience changed: take the post out of every inbox, then push it to the current audience."""
    from posts.models import Post

    post = Post.objects.filter(pk=post_id).first()
    if post is not None:
        candidates.retract(post)
        candidates.fan_out(post)


@shared_task(name='feedcache.tasks.retract_post', queue='default', ignore_result=True)
def retract_post(post_id, author_id, group_id=None, page_id=None):
    # The row is gone, so the task gets the fields audience() needs.
    candidates.retract(SimpleNamespace(id=post_id, author_id=author_id, group_id=group_id, page_id=page_id,
                                       privacy=None, moderation_status=None))
