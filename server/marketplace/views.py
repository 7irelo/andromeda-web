from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.Views import APIView
from .models import Post, Comment, User
from .forms import PostForm, UserForm, MyUserCreationForm
from .serializers import ItemSerializer
import jwt, datetime

class MarketplaceView(APIView):
    def get(self, request):
        q = request.GET.get("q") if request.GET.get("q") != None else ""
        items = Item.objects.filter(Q(user__name__icontains=q) | Q(text__icontains=q))
        item_count = items.count()
        comments = Comment.objects.filter(Q(post___text___icontains=q))
        serializer = ItemSerializer(items, many=True)
        return Response(serializer.data)

class ItemView(APIView):
    def get(self, request, pk):
        item = Items.objects.get(id=pk)
        comments = item.comment_set.all().order_by("created")
        participants = item.participants.all()
        serializer = ItemSerializer(item, many=False)
        return Response(serializer.data)

    def post(self, request, pk):
        item = Item.objects.get(id=pk)
        comments = Comment.objects.create(
            user=request.user,
            item=item,
            text=request.POST.get("text")
        )
        item.participants.add(request.user)
        serializer = ItemSerializer(item, many=False)
        return Response(serializer.data)
