"""
Marketplace side effects, queued after the transaction commits.
"""
import logging
from decimal import Decimal

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='marketplace.tasks.notify_price_drop', queue='notifications')
def notify_price_drop(listing_id, old_price):
    """Tell everyone who saved a listing that its price came down."""
    from core import visibility
    from notifications.models import Notification
    from notifications.service import notify
    from .models import Listing, ListingLike

    listing = Listing.objects.select_related('seller').filter(pk=listing_id).first()
    if listing is None or listing.status not in Listing.PUBLIC_STATUSES or listing.moderation_status == 'removed':
        return 0
    old_price = Decimal(str(old_price))
    if listing.price >= old_price:
        return 0  # raised again before the task ran
    # Blocks hide content both ways, so neither side of a block hears about the other's listings.
    recipients = ListingLike.objects.filter(listing=listing).exclude(user_id=listing.seller_id).exclude(
        user_id__in=visibility.blocked_ids(listing.seller)).values_list('user_id', flat=True)
    title = f'Price drop: {listing.title[:150]} is now {listing.currency} {listing.price}'
    extra = {'kind': 'price_drop', 'listing_id': listing.id, 'old_price': str(old_price),
             'new_price': str(listing.price), 'currency': listing.currency}
    sent = 0
    # notify() applies each saver's Marketplace preferences (in-app, push, email) and blocks again.
    for uid in list(recipients):
        if notify(uid, Notification.TYPE_SYSTEM, title, sender=listing.seller, extra=extra,
                  push_url=f'/marketplace/{listing.id}'):
            sent += 1
    logger.info('Price drop on listing %s notified %d savers', listing.id, sent)
    return sent
