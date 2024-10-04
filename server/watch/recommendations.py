from .models import Video
from users.models import User

def get_recommended_videos(user: User):
    liked_videos = Video.nodes.filter(likes=user)
    similar_users = User.nodes.filter(video_likes__in=liked_videos).exclude(uid=user.uid).distinct()
    recommended_videos = Video.nodes.filter(likes__in=similar_users).exclude(likes=user).distinct()
    user_liked_tags = Video.nodes.filter(likes=user).values_list('tags', flat=True)
    
    if user_liked_tags:
        recommended_videos = recommended_videos.filter(tags__in=user_liked_tags).distinct()
    user_friends = user.friends.all()
   
    if user_friends.exists():
        recommended_videos = recommended_videos.filter(creator__in=user_friends).distinct()
    recommended_videos = recommended_videos.order_by('-num_likes', '-created')[:10]
   
    return recommended_videos
