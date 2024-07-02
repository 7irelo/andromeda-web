from django.shortcuts import get_object_or_404
from django.db.models import Q, Case, When, Value, IntegerField
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Product, ProductComment
from .serializers import ProductSerializer, ProductCommentSerializer
from .recommendations import get_recommended_products

class RecommendedProductsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        recommended_products = get_recommended_products(user)
        serializer = ProductSerializer(recommended_products, many=True)
        return Response(serializer.data)


class ProductsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.GET.get("q", "")
        
        # Define relevance order conditions
        relevance_order = Case(
            When(creator__friends=request.user, then=Value(1)),
            When(likes=request.user, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
        
        # Query products ordered by relevance
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(tags__name__icontains=query)
        ).annotate(
            relevance=relevance_order
        ).order_by('relevance').select_related('creator').prefetch_related('participants', 'tags')

        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save(creator=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        product = get_object_or_404(Product.objects.select_related('creator').prefetch_related('participants', 'tags'), pk=pk)
        comments = ProductComment.objects.filter(product=product).select_related('user').order_by("created")
        product_serializer = ProductSerializer(product)
        comments_serializer = ProductCommentSerializer(comments, many=True)
        return Response({
            "product": product_serializer.data,
            "comments": comments_serializer.data
        })

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        serializer = ProductCommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, product=product)
            product.participants.add(request.user)
            return Response({
                "product": ProductSerializer(product).data,
                "comment": ProductCommentSerializer(comment).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        serializer = ProductSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductCommentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_pk, pk):
        comment = get_object_or_404(ProductComment.objects.select_related('user', 'product'), product_id=product_pk, pk=pk)
        serializer = ProductCommentSerializer(comment)
        return Response(serializer.data)

    def post(self, request, product_pk):
        product = get_object_or_404(Product, pk=product_pk)
        serializer = ProductCommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, product_pk, pk):
        comment = get_object_or_404(ProductComment, product_id=product_pk, pk=pk)
        serializer = ProductCommentSerializer(comment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, product_pk, pk):
        comment = get_object_or_404(ProductComment, product_id=product_pk, pk=pk)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
