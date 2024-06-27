from django.contrib import messages
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Item, ItemComment
from .serializers import ItemSerializer
import jwt, datetime

class MarketplaceView(APIView):
    def get(self, request):
        # Get query parameter or set default to empty string
        q = request.GET.get("q", "")
        # Filter items based on query parameter
        items = Item.objects.filter(Q(user__name__icontains=q) | Q(text__icontains=q))
        # Get count of filtered items (not used in the response, so could be removed)
        item_count = items.count()
        # Filter comments based on query parameter (changed to ItemComment)
        comments = ItemComment.objects.filter(Q(post__text__icontains=q))
        # Serialize filtered items
        serializer = ItemSerializer(items, many=True)
        return Response(serializer.data)

class ItemView(APIView):
    def get(self, request, pk):
        try:
            # Retrieve the item by primary key
            item = Item.objects.get(id=pk)
        except Item.DoesNotExist:
            return Response({'error': 'Item not found'}, status=404)
        
        # Retrieve related comments and participants
        comments = item.itemcomment_set.all().order_by("created")
        participants = item.participants.all()
        # Serialize the item
        serializer = ItemSerializer(item, many=False)
        return Response(serializer.data)

    def post(self, request, pk):
        try:
            # Retrieve the item by primary key
            item = Item.objects.get(id=pk)
        except Item.DoesNotExist:
            return Response({'error': 'Item not found'}, status=404)
        
        # Create a new comment for the item
        comment = ItemComment.objects.create(
            user=request.user,
            item=item,
            text=request.data.get("text")  # Use request.data instead of request.POST
        )
        # Add the user to the participants of the item
        item.participants.add(request.user)
        # Serialize the updated item
        serializer = ItemSerializer(item, many=False)
        return Response(serializer.data)
