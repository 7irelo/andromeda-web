# Generated migration for Phase B changes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_alter_user_email_and_more'),
    ]

    operations = [
        # Remove Follow model
        migrations.DeleteModel(
            name='Follow',
        ),
        # Remove follower/following counters from User
        migrations.RemoveField(
            model_name='user',
            name='followers_count',
        ),
        migrations.RemoveField(
            model_name='user',
            name='following_count',
        ),
        # Add privacy fields
        migrations.AddField(
            model_name='user',
            name='privacy_profile',
            field=models.CharField(
                choices=[('everyone', 'Everyone'), ('friends', 'Friends'), ('private', 'Only Me')],
                default='everyone', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='privacy_messages',
            field=models.CharField(
                choices=[('everyone', 'Everyone'), ('friends', 'Friends'), ('nobody', 'Nobody')],
                default='everyone', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='privacy_friend_requests',
            field=models.CharField(
                choices=[('everyone', 'Everyone'), ('friends_of_friends', 'Friends of Friends'), ('nobody', 'Nobody')],
                default='everyone', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='privacy_friends_list',
            field=models.CharField(
                choices=[('everyone', 'Everyone'), ('friends', 'Friends'), ('private', 'Only Me')],
                default='everyone', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='default_post_privacy',
            field=models.CharField(
                choices=[('public', 'Public'), ('friends', 'Friends'), ('private', 'Only Me')],
                default='public', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='show_online_status',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='searchable',
            field=models.BooleanField(default=True),
        ),
    ]
