from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    path('login/',
         LoginView.as_view
         (
             template_name='profiles/login.html',
             authentication_form=forms.BootstrapAuthenticationForm,
             extra_context=
             {
                 'title': 'Log in',
                 'year' : datetime.now().year,
             }
         ),
         name='login'),
    path('logout/', LogoutView.as_view(next_page='/'), name='logout'),
    
    # path('login/', views.loginPage, name="login"),
    # path('logout/', views.logoutUser, name="logout"),
    # path('register/', views.registerPage, name="register"),
    path('register/', RegisterView.as_view()),
    
    path("post/<str:pk>/", views.post, name="post"),
    path("profile/<str:pk>/", views.userProfile, name="user-profile"),

    path("create-post", views.createPost, name="create-post"),
    path("update-post/<str:pk>/", views.updateRoom, name="update-room"),
    path("delete-post/<str:pk>/", views.deleteRoom, name="delete-room"),
    path("delete-comment/<str:pk>/", views.deleteComment, name="delete-comment"),

    path("profile/update-user/", views.updateUser, name="update-user"),
]
