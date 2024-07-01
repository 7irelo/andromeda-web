urlpatterns = [
    path('/', UserView.as_view(), name='users'),
    path('<str:username>/', UserView.as_view(), name='profile'),
]
