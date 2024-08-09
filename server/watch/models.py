from neomodel import StructuredNode, StringProperty, DateTimeProperty, RelationshipTo, RelationshipFrom, UniqueIdProperty
from users.models import User
from pages.models import Page  # Assuming Page model is in your pages app
from datetime import datetime

class VideoCategory(StructuredNode):
    name = StringProperty(unique_index=True, required=True)

class Video(StructuredNode):
    uid = UniqueIdProperty()
    title = StringProperty(required=True)
    description = StringProperty()
    url = StringProperty(required=True)  # URL to the video file or streaming link
    uploaded_by = RelationshipTo(User, 'UPLOADED_BY')
    posted_on_page = RelationshipTo(Page, 'POSTED_ON_PAGE')  # If video is posted by a page
    likes = RelationshipTo(User, 'LIKED_BY')
    categories = RelationshipTo(VideoCategory, 'BELONGS_TO_CATEGORY')
    tags = StringProperty()  # Comma-separated tags
    views = RelationshipTo(User, 'VIEWED_BY')
    updated = DateTimeProperty(default=datetime.utcnow)
    created = DateTimeProperty(default=datetime.utcnow)

class VideoLike(StructuredNode):
    user = RelationshipTo(User, 'LIKED_BY')
    video = RelationshipFrom(Video, 'HAS_LIKE')
    created_at = DateTimeProperty(default=datetime.utcnow)

class VideoComment(StructuredNode):
    user = RelationshipTo(User, 'COMMENTED_BY')
    video = RelationshipFrom(Video, 'HAS_COMMENT')
    text = StringProperty(required=True)
    updated = DateTimeProperty(default=datetime.utcnow)
    created = DateTimeProperty(default=datetime.utcnow)
