from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from core import visibility
from moderation.tasks import queue_moderation
from core.permissions import IsOwnerOrReadOnly
from core.validators import sanitize_image
from .models import Listing, ListingImage, ListingLike, Category
from .serializers import ListingSerializer, ListingImageSerializer, CategorySerializer, ReviewSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(parent=None)
    serializer_class = CategorySerializer
    permission_classes = []


MAX_IMAGES_PER_LISTING = 10


def _clean_images(files, existing=0):
    if existing + len(files) > MAX_IMAGES_PER_LISTING:
        raise ValidationError({'images': f'A listing can have at most {MAX_IMAGES_PER_LISTING} images.'})
    try:
        return [sanitize_image(f) for f in files]
    except DjangoValidationError as exc:
        raise ValidationError({'images': exc.messages})


class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer
    permission_classes = [IsOwnerOrReadOnly]
    owner_field = 'seller'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if self.request.query_params.get('mine') == 'true':
            return Listing.objects.filter(seller=self.request.user).select_related(
                'seller', 'category').prefetch_related('images')
        qs = Listing.objects.filter(
            (Q(status=Listing.STATUS_ACTIVE) & ~Q(moderation_status='removed')) | Q(seller=self.request.user)
        ).exclude(seller_id__in=visibility.blocked_ids(self.request.user)).select_related('seller', 'category')
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)
        search = self.request.query_params.get('search')
        if search:
            search = search.strip()[:100]
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        try:
            if min_price:
                qs = qs.filter(price__gte=float(min_price))
            if max_price:
                qs = qs.filter(price__lte=float(max_price))
        except ValueError:
            raise ValidationError({'detail': 'Prices must be numbers.'})
        return qs.prefetch_related('images')

    def perform_create(self, serializer):
        images = _clean_images(self.request.FILES.getlist('images'))
        listing = serializer.save(seller=self.request.user)
        queue_moderation('listing', listing.id)
        for i, img in enumerate(images):
            ListingImage.objects.create(listing=listing, image=img, is_primary=(i == 0), order=i)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.seller_id != request.user.id:
            Listing.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        listing = self.get_object()
        like, created = ListingLike.objects.get_or_create(user=request.user, listing=listing)
        if not created:
            like.delete()
            Listing.objects.filter(pk=listing.pk).update(likes_count=listing.liked_by.count())
            return Response({'liked': False})
        Listing.objects.filter(pk=listing.pk).update(likes_count=listing.liked_by.count())
        return Response({'liked': True})

    @action(detail=True, methods=['post'])
    def upload_images(self, request, pk=None):
        listing = self.get_object()
        if listing.seller != request.user:
            return Response({'detail': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)
        current_count = listing.images.count()
        images = _clean_images(request.FILES.getlist('images'), current_count)
        if not images:
            return Response({'detail': 'No images provided.'}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        for i, img in enumerate(images):
            obj = ListingImage.objects.create(
                listing=listing, image=img, order=current_count + i
            )
            created.append(obj)
        return Response(
            ListingImageSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get', 'post'])
    def reviews(self, request, pk=None):
        listing = self.get_object()
        if request.method == 'GET':
            return Response(ReviewSerializer(
                listing.reviews.select_related('reviewer').all(),
                many=True, context={'request': request}
            ).data)
        if listing.seller_id == request.user.id:
            raise PermissionDenied('You cannot review your own listing.')
        if listing.reviews.filter(reviewer=request.user).exists():
            raise ValidationError({'detail': 'You already reviewed this listing.'})
        serializer = ReviewSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(reviewer=request.user, listing=listing)
        return Response(serializer.data, status=201)
