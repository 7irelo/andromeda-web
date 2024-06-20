from django.forms import ModelForm
from django.contrib.auth.forms import UserCreationForm
from .models import Post, User

class MyUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "password1", "password2"]

class PostForm(ModelForm):
    class Meta:
        model = Post
        fields = "__all__"
        exclude = ["host", "participants"]

class UserForm(ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
