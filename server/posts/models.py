from django.conf import settings
from django.db import models


class Post(models.Model):
    TYPE_TEXT = 'text'
    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_LINK = 'link'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_LINK, 'Link'),
    ]

    PRIVACY_PUBLIC = 'public'
    PRIVACY_FRIENDS = 'friends'
    PRIVACY_PRIVATE = 'private'
    PRIVACY_CHOICES = [
        (PRIVACY_PUBLIC, 'Public'),
        (PRIVACY_FRIENDS, 'Friends'),
        (PRIVACY_PRIVATE, 'Only Me'),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='posts', on_delete=models.CASCADE
    )
    content = models.TextField(blank=True)
    post_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_TEXT)
    privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default=PRIVACY_PUBLIC)

    # Media
    image = models.ImageField(upload_to='posts/images/%Y/%m/', null=True, blank=True)
    video = models.FileField(upload_to='posts/videos/%Y/%m/', null=True, blank=True)
    link_url = models.URLField(blank=True)
    link_title = models.CharField(max_length=255, blank=True)
    link_description = models.TextField(blank=True)
    link_image = models.URLField(blank=True)

    # Context (group / page)
    group = models.ForeignKey(
        'groups.Group', null=True, blank=True, related_name='posts', on_delete=models.SET_NULL
    )
    page = models.ForeignKey(
        'pages.Page', null=True, blank=True, related_name='posts', on_delete=models.SET_NULL
    )

    # Counters
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)

    # Share
    shared_post = models.ForeignKey(
        'self', null=True, blank=True, related_name='shares', on_delete=models.SET_NULL
    )

    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'posts'
        ordering = ['-created_at']

    def __str__(self):
        return f'Post by {self.author.username} @ {self.created_at:%Y-%m-%d}'


class PostMedia(models.Model):
    post = models.ForeignKey(Post, related_name='media', on_delete=models.CASCADE)
    file = models.FileField(upload_to='posts/media/%Y/%m/')
    media_type = models.CharField(max_length=10, choices=[('image', 'Image'), ('video', 'Video')])
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'post_media'
        ordering = ['order']


class Like(models.Model):
    REACTION_LIKE = 'like'
    REACTION_LOVE = 'love'
    REACTION_HAHA = 'haha'
    REACTION_WOW = 'wow'
    REACTION_SAD = 'sad'
    REACTION_ANGRY = 'angry'
    REACTION_CHOICES = [
        (REACTION_LIKE, 'Like'),
        (REACTION_LOVE, 'Love'),
        (REACTION_HAHA, 'Haha'),
        (REACTION_WOW, 'Wow'),
        (REACTION_SAD, 'Sad'),
        (REACTION_ANGRY, 'Angry'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='likes', on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='likes', on_delete=models.CASCADE)
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES, default=REACTION_LIKE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'likes'
        unique_together = ('user', 'post')


class Comment(models.Model):
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='comments', on_delete=models.CASCADE
    )
    content = models.TextField()
    parent = models.ForeignKey(
        'self', null=True, blank=True, related_name='replies', on_delete=models.CASCADE
    )
    likes_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'comments'
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author.username} on Post {self.post_id}'


class PostTag(models.Model):
    post = models.ForeignKey(Post, related_name='tags', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'post_tags'
        unique_together = ('post', 'name')
