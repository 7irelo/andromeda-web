from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import PageNode, PagePostNode
from .serializers import PageSerializer, PagePostSerializer
from users.models import UserNode  # Assuming you have a UserNode model

class PageListView(APIView):
    def get(self, request):
        pages = PageNode.nodes.order_by('-created')
        serializer = PageSerializer(pages, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PageSerializer(data=request.data)
        if serializer.is_valid():
            user_node = UserNode.nodes.get(uid=request.user.uid)  # Get the user node
            page = serializer.save()
            page.creator.connect(user_node)
            return Response(PageSerializer(page).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PageDetailView(APIView):
    def get(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        posts = page.posts.order_by('-created')
        page_serializer = PageSerializer(page)
        posts_serializer = PagePostSerializer(posts, many=True)
        return Response({
            "page": page_serializer.data,
            "posts": posts_serializer.data
        })

    def put(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        serializer = PageSerializer(page, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        page.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class PageFollowView(APIView):
    def post(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        user_node = UserNode.nodes.get(uid=request.user.uid)
        page.followers.connect(user_node)
        return Response({'message': 'Page followed successfully'}, status=status.HTTP_200_OK)

    def delete(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        user_node = UserNode.nodes.get(uid=request.user.uid)
        page.followers.disconnect(user_node)
        return Response({'message': 'Page unfollowed successfully'}, status=status.HTTP_204_NO_CONTENT)

class PageLikeView(APIView):
    def post(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        user_node = UserNode.nodes.get(uid=request.user.uid)
        page.likes.connect(user_node)
        return Response({'message': 'Page liked successfully'}, status=status.HTTP_200_OK)

    def delete(self, request, uid):
        page = get_object_or_404(PageNode, uid=uid)
        user_node = UserNode.nodes.get(uid=request.user.uid)
        page.likes.disconnect(user_node)
        return Response({'message': 'Page unliked successfully'}, status=status.HTTP_204_NO_CONTENT)
