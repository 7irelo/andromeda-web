from .models import Product
from users.models import User

def get_recommended_products(user: User):
    liked_posts = Product.nodes.filter(likes=user)
    similar_users = User.nodes.filter(post_likes__in=liked_posts).exclude(uid=user.uid).distinct()
    recommended_products = Product.nodes.filter(likes__in=similar_users).exclude(likes=user).distinct()
    user_liked_tags = Product.nodes.filter(likes=user).values_list('tags', flat=True)
    
    if user_liked_tags:
        recommended_products = recommended_products.filter(tags__in=user_liked_tags).distinct()
    user_friends = user.friends.all()
   
    if user_friends.exists():
        recommended_products = recommended_products.filter(creator__in=user_friends).distinct()
    recommended_products = recommended_products.order_by('-num_likes', '-created')[:10]
   
    return recommended_products
