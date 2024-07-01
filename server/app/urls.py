from django.urls import path
from .views import RegisterView, LoginView, LogoutView, UserView, HomeView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('home/', HomeView.as_view(), name='home'),
    # Additional paths for other views if needed
]

