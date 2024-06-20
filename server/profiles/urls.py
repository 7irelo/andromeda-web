from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.loginPage, name="login"),
    path('logout/', views.logoutUser, name="logout"),
    path('register/', views.registerPage, name="register"),

    path('', views.home, name="home"),
    path("post/<str:pk>/", views.post, name="post"),
    path("profile/<str:pk>/", views.userProfile, name="user-profile"),

    path("create-post", views.createPost, name="create-post"),
    path("update-post/<str:pk>/", views.updateRoom, name="update-room"),
    path("delete-post/<str:pk>/", views.deleteRoom, name="delete-room"),
    path("delete-comment/<str:pk>/", views.deleteComment, name="delete-comment"),

    path("profile/update-user/", views.updateUser, name="update-user"),
]
