from django.urls import path
from .views import RecommendedProductsView, ProductsView, ProductView, ProductCommentView

urlpatterns = [
    path('recommended/', RecommendedProductsView.as_view(), name='recommended-products'),
    path('', ProductsView.as_view(), name='products'),
    path('<int:pk>/', ProductView.as_view(), name='product-detail'),
    path('<int:product_pk>/comments/<int:pk>/', ProductCommentView.as_view(), name='product-comment-detail'),
    path('<int:product_pk>/comments/', ProductCommentView.as_view(), name='product-comment-create'),
]
