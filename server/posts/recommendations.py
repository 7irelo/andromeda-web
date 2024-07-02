from .models import Post, User

def get_recommended_posts(user: User):
    """
    Get a list of recommended posts for the given user.

    Recommendations are based on:
    - Posts liked by users who have liked the same posts as the given user.
    - Excludes posts already liked by the given user.
    """
    # Step 1: Get posts liked by the user
    liked_posts = Post.objects.filter(likes=user)
    
    # Step 2: Get users who liked the same posts
    similar_users = User.objects.filter(post_likes__in=liked_posts).exclude(id=user.id).distinct()

    # Step 3: Get posts liked by similar users but not yet liked by the current user
    recommended_posts = Post.objects.filter(likes__in=similar_users).exclude(likes=user).distinct()

    return recommended_posts
