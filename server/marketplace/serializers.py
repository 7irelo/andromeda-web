from rest_framework import serializers
from .models import Item, ItemComment

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'host', 'text', 'participants']

    def create(self, validated_data):
        # Create a new instance of Item with the validated data
        instance = Item.objects.create(**validated_data)
        return instance

class ItemCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemComment
        fields = ['id', 'user', 'item', 'text']

    def create(self, validated_data):
        # Create a new instance of ItemComment with the validated data
        instance = ItemComment.objects.create(**validated_data)
        return instance
