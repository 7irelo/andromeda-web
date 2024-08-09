from celery import shared_task
from .models import Notification
from users.models import User
from datetime import datetime

@shared_task
def send_daily_birthday_notifications():
    today = datetime.today().date()
    users_with_birthdays = User.objects.filter(date_of_birth=today)
    for user in users_with_birthdays:
        for friend in user.friends.all():
            Notification.objects.create(
                user=friend,
                message=f'Today is {user.username}\'s birthday!',
                notification_type='birthday'
            )
