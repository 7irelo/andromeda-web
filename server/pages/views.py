from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Page, PagePost
from .serializers import PageSerializer, PagePostSerializer
from users.models import User

class PageListView(APIView):
    def get(self, request):
        pages = Page.nodes.order_by('-created')
        serializer = PageSerializer(pages, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PageSerializer(data=request.data)
        if serializer.is_valid():
            user = User.nodes.get(uid=request.user.uid)  # Get the user node
            page = serializer.save()
            page.creator.connect(user)
            return Response(PageSerializer(page).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PageDetailView(APIView):
    def get(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        posts = page.posts.order_by('-created')
        page_serializer = PageSerializer(page)
        posts_serializer = PagePostSerializer(posts, many=True)
        return Response({
            "page": page_serializer.data,
            "posts": posts_serializer.data
        })

    def put(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        serializer = PageSerializer(page, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        page.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class PageFollowView(APIView):
    def post(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        user = User.nodes.get(uid=request.user.uid)
        page.followers.connect(user)
        return Response({'message': 'Page followed successfully'}, status=status.HTTP_200_OK)

    def delete(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        user = User.nodes.get(uid=request.user.uid)
        page.followers.disconnect(user)
        return Response({'message': 'Page unfollowed successfully'}, status=status.HTTP_204_NO_CONTENT)

class PageLikeView(APIView):
    def post(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        user = User.nodes.get(uid=request.user.uid)
        page.likes.connect(user)
        return Response({'message': 'Page liked successfully'}, status=status.HTTP_200_OK)

    def delete(self, request, uid):
        page = get_object_or_404(Page, uid=uid)
        user = User.nodes.get(uid=request.user.uid)
        page.likes.disconnect(user)
        return Response({'message': 'Page unliked successfully'}, status=status.HTTP_204_NO_CONTENT)
