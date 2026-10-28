from django.db.models import Avg, Count
from rest_framework import serializers
from .models import Listing, ListingImage, Category, Review
from . import geo
from users.serializers import UserSerializer


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon', 'parent']


class CategoryTreeSerializer(CategorySerializer):
    children = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ['children']

    def get_children(self, obj):
        # Children are prefetched by the view, so the tree costs two queries in total.
        return CategorySerializer(sorted(obj.children.all(), key=lambda c: c.name), many=True).data


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ['id', 'image', 'is_primary', 'order']


def _rating(avg, count):
    return {'average': round(float(avg), 2) if avg is not None and count else None, 'count': count or 0}


def seller_rating(seller_id):
    agg = Review.objects.filter(listing__seller_id=seller_id).aggregate(avg=Avg('rating'), count=Count('id'))
    return _rating(agg['avg'], agg['count'])


class ListingSerializer(serializers.ModelSerializer):
    seller = UserSerializer(read_only=True)
    images = ListingImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    # Coordinates are write-only: what comes back is rounded, and only the seller sees their own.
    latitude = serializers.FloatField(write_only=True, required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(write_only=True, required=False, allow_null=True,
                                       min_value=-180, max_value=180)
    approx_point = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    seller_rating = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            'id', 'seller', 'title', 'description', 'price', 'currency',
            'condition', 'category', 'category_id', 'location', 'latitude', 'longitude',
            'approx_point', 'distance_km', 'status', 'views_count', 'likes_count', 'images', 'is_liked',
            'rating', 'seller_rating', 'created_at', 'updated_at',
        ]
        read_only_fields = ['seller', 'views_count', 'likes_count']

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Price cannot be negative.')
        return value

    def validate(self, attrs):
        lat, lng = attrs.get('latitude', ...), attrs.get('longitude', ...)
        if (lat is ...) != (lng is ...) or ((lat is None) != (lng is None)):
            raise serializers.ValidationError({'latitude': 'Send latitude and longitude together.'})
        if lat is not ... and lat is not None:
            attrs['latitude'], attrs['longitude'] = geo.snap(lat), geo.snap(lng)
        elif lat is ... and 'location' in attrs and (self.instance is None
                                                     or attrs['location'] != self.instance.location):
            # No shared position: fall back to the centroid of the city in the location text.
            point = geo.centroid_for(attrs['location'])
            attrs['latitude'], attrs['longitude'] = (geo.snap(point[0]), geo.snap(point[1])) if point else (
                None, None)
        return attrs

    def _viewer_id(self):
        request = self.context.get('request')
        return request.user.id if request and request.user.is_authenticated else None

    def get_approx_point(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return None
        if obj.seller_id == self._viewer_id():
            return {'latitude': obj.latitude, 'longitude': obj.longitude}
        return {'latitude': geo.public(obj.latitude), 'longitude': geo.public(obj.longitude)}

    def get_distance_km(self, obj):
        d = getattr(obj, 'distance', None)
        # Whole kilometres, at least 1: finer steps would help triangulate the seller.
        return None if d is None else max(1, round(d))

    def get_is_liked(self, obj):
        if hasattr(obj, 'is_liked_annotated'):
            return bool(obj.is_liked_annotated)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.liked_by.filter(user=request.user).exists()
        return False

    def get_rating(self, obj):
        if hasattr(obj, 'rating_avg'):
            return _rating(obj.rating_avg, obj.rating_count)
        agg = obj.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
        return _rating(agg['avg'], agg['count'])

    def get_seller_rating(self, obj):
        if hasattr(obj, 'seller_rating_avg'):
            return _rating(obj.seller_rating_avg, obj.seller_rating_count)
        return seller_rating(obj.seller_id)


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'listing', 'reviewer', 'rating', 'comment', 'created_at']
        read_only_fields = ['listing', 'reviewer']
        extra_kwargs = {'comment': {'max_length': 2000}}

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value


class DraftRequestSerializer(serializers.Serializer):
    hint = serializers.CharField(required=False, allow_blank=True, max_length=500, trim_whitespace=True)
    currency = serializers.CharField(required=False, max_length=3, min_length=3, default='ZAR')

    def validate_currency(self, value):
        if not value.isalpha():
            raise serializers.ValidationError('Use a three-letter currency code.')
        return value.upper()
