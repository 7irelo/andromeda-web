from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Listing, ListingImage, ListingLike, Category, Review
from .serializers import ListingSerializer, ListingImageSerializer, CategorySerializer, ReviewSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(parent=None)
    serializer_class = CategorySerializer
    permission_classes = []


class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer

    def get_queryset(self):
        qs = Listing.objects.filter(status=Listing.STATUS_ACTIVE).select_related('seller', 'category')
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(title__icontains=search)
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            qs = qs.filter(price__gte=min_price)
        if max_price:
            qs = qs.filter(price__lte=max_price)
        mine = self.request.query_params.get('mine')
        if mine == 'true':
            qs = Listing.objects.filter(seller=self.request.user)
        return qs.prefetch_related('images')

    def perform_create(self, serializer):
        listing = serializer.save(seller=self.request.user)
        images = self.request.FILES.getlist('images')
        for i, img in enumerate(images):
            ListingImage.objects.create(listing=listing, image=img, is_primary=(i == 0), order=i)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Listing.objects.filter(pk=instance.pk).update(views_count=instance.views_count + 1)
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
        images = request.FILES.getlist('images')
        if not images:
            return Response({'detail': 'No images provided.'}, status=status.HTTP_400_BAD_REQUEST)
        current_count = listing.images.count()
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
        serializer = ReviewSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(reviewer=request.user, listing=listing)
        return Response(serializer.data, status=201)
