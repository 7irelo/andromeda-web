from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Video, VideoComment
from .serializers import VideoSerializer, VideoCommentSerializer

class RecommendedVideosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        recommended_videos = get_recommended_videos(user)  # You will implement this in recommendations.py
        serializer = VideoSerializer(recommended_videos, many=True)
        return Response(serializer.data)

class VideosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.GET.get("q", "")
        videos = Video.nodes.filter(title__icontains=query)
        serializer = VideoSerializer(videos, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = VideoSerializer(data=request.data)
        if serializer.is_valid():
            video = serializer.save(uploaded_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VideoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        video = get_object_or_404(Video, uid=pk)
        comments = VideoComment.nodes.filter(video=video)
        video_serializer = VideoSerializer(video)
        comments_serializer = VideoCommentSerializer(comments, many=True)
        return Response({
            "video": video_serializer.data,
            "comments": comments_serializer.data
        })

    def post(self, request, pk):
        video = get_object_or_404(Video, uid=pk)
        serializer = VideoCommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, video=video)
            video.views.connect(request.user)
            return Response({
                "video": VideoSerializer(video).data,
                "comment": VideoCommentSerializer(comment).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        video = get_object_or_404(Video, uid=pk)
        serializer = VideoSerializer(video, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        video = get_object_or_404(Video, uid=pk)
        video.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class VideoCommentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, video_pk, pk):
        comment = get_object_or_404(VideoComment, uid=pk)
        serializer = VideoCommentSerializer(comment)
        return Response(serializer.data)

    def post(self, request, video_pk):
        video = get_object_or_404(Video, uid=video_pk)
        serializer = VideoCommentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, video=video)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, video_pk, pk):
        comment = get_object_or_404(VideoComment, uid=pk)
        serializer = VideoCommentSerializer(comment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, video_pk, pk):
        comment = get_object_or_404(VideoComment, uid=pk)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
