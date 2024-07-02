from django.db.models import Count
from .models import Post, User

def get_recommended_posts(user: User):
    liked_posts = Post.objects.filter(likes=user)
    similar_users = User.objects.filter(post_likes__in=liked_posts).exclude(id=user.id).distinct()
    recommended_posts = Post.objects.filter(likes__in=similar_users).exclude(likes=user).distinct()
    user_liked_tags = Post.objects.filter(likes=user).values_list('tags', flat=True)
    
    if user_liked_tags:
        recommended_posts = recommended_posts.filter(tags__in=user_liked_tags).distinct()
    user_friends = user.friends.all()
   
    if user_friends.exists():
        recommended_posts = recommended_posts.filter(creator__in=user_friends).distinct()
    recommended_posts = recommended_posts.annotate(num_likes=Count('likes')).order_by('-num_likes', '-created')[:10]
   
    return recommended_posts
