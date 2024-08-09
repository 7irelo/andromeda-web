from rest_framework import serializers
from .models import Product, ProductComment

class ProductSerializer(serializers.Serializer):
    uid = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField()
    price = serializers.FloatField()
    updated = serializers.DateTimeField()
    created = serializers.DateTimeField()

    def create(self, validated_data):
        return Product(**validated_data).save()

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

class ProductCommentSerializer(serializers.Serializer):
    uid = serializers.CharField(read_only=True)
    text = serializers.CharField()
    updated = serializers.DateTimeField()
    created = serializers.DateTimeField()

    def create(self, validated_data):
        return ProductComment(**validated_data).save()

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance
