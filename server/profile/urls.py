urlpatterns = [
    path('<str:username>/', UserView.as_view(), name='profile'),
]
