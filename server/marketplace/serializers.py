from rest_framework import serializers
from .models import Listing, ListingImage, Category, Review
from users.serializers import UserSerializer


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon', 'parent']


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ['id', 'image', 'is_primary', 'order']


class ListingSerializer(serializers.ModelSerializer):
    seller = UserSerializer(read_only=True)
    images = ListingImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False
    )
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            'id', 'seller', 'title', 'description', 'price', 'currency',
            'condition', 'category', 'category_id', 'location', 'status',
            'views_count', 'likes_count', 'images', 'is_liked',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['seller', 'views_count', 'likes_count']

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.liked_by.filter(user=request.user).exists()
        return False


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'listing', 'reviewer', 'rating', 'comment', 'created_at']
        read_only_fields = ['reviewer']
