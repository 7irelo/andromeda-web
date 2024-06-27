from rest_framework import serializers
from .models import Item, ItemComment

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['host', 'text', 'participants']
 
    def create(self, validated_data):
        instance = self.Meta.model(**validated_data)
        instance.save()
        return instance

class ItemCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemComment
        fields = ['user', 'item', 'text']
 
    def create(self, validated_data):
        instance = self.Meta.model(**validated_data)
        instance.save()
        return instance
