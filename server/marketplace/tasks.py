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
    from notifications.tasks import _push_to_websocket
    from .models import Listing, ListingLike

    listing = Listing.objects.select_related('seller').filter(pk=listing_id).first()
    if listing is None or listing.status not in Listing.PUBLIC_STATUSES or listing.moderation_status == 'removed':
        return 0
    old_price = Decimal(str(old_price))
    if listing.price >= old_price:
        return 0  # raised again before the task ran
    # Blocks hide content both ways, so neither side of a block hears about the other's listings.
    recipients = list(ListingLike.objects.filter(listing=listing).exclude(user_id=listing.seller_id).exclude(
        user_id__in=visibility.blocked_ids(listing.seller)).values_list('user_id', flat=True))
    if not recipients:
        return 0
    title = f'Price drop: {listing.title[:150]} is now {listing.currency} {listing.price}'
    extra = {'kind': 'price_drop', 'listing_id': listing.id, 'old_price': str(old_price),
             'new_price': str(listing.price), 'currency': listing.currency}
    notes = Notification.objects.bulk_create([
        Notification(recipient_id=uid, sender=listing.seller, notification_type=Notification.TYPE_SYSTEM,
                     title=title, extra=extra)
        for uid in recipients
    ])
    for n in notes:
        if n.pk:
            _push_to_websocket(n.recipient_id, {'id': n.pk, 'type': Notification.TYPE_SYSTEM, 'title': title,
                                                'sender': listing.seller.username, **extra})
    logger.info('Price drop on listing %s notified %d savers', listing.id, len(notes))
    return len(notes)
