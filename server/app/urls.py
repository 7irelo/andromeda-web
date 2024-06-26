from django.urls import path
from . import views
from views import RegisterView, LoginView, UserView, UpdateUser, LogoutView, HomeView, PostView, CreatePost, UpdatePost, DeletePost, DeleteComment

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    path('login/',
         LoginView.as_view
         (
             # template_name='profiles/login.html',
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
    
    path("post/<str:pk>/", PostView, name="post"),
    path("profile/<str:pk>/", UserView, name="profile"),

    path("create-post", CreatePost, name="create-post"),
    path("update-post/<str:pk>/", UpdatePost, name="update-post"),
    path("delete-post/<str:pk>/", DeletePost, name="delete-post"),
    path("delete-comment/<str:pk>/", DeleteComment, name="delete-comment"),

    path("profile/update-user/", UpdateUser, name="update-user"),
]
