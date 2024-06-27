from django.urls import path
from .views import RegisterView, LoginView, UserView, UpdateUserView, LogoutView, HomeView

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    # Authentication
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    # Profile
    path('<str:pk>/', UserView.as_view(), name='profile'),
    path('update-user/', UpdateUserView.as_view(), name='update-user'),
]
