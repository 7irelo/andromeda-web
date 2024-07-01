from .models import Post, User

def get_recommended_posts(user: User):
    # Get posts liked by the user
    liked_posts = Post.objects.filter(likes=user)
    
    # Get users who liked the same posts
    similar_users = User.objects.filter(post_likes__in=liked_posts).exclude(id=user.id).distinct()

    # Get posts liked by similar users but not yet liked by the current user
    recommended_posts = Post.objects.filter(likes__in=similar_users).exclude(likes=user).distinct()

    return recommended_posts
