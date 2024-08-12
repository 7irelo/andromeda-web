from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    friends = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['uid', 'username', 'first_name', 'last_name', 'avatar', 'bio', 'email', 'friends']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def get_friends(self, obj):
        friends = obj.friends.all()
        return SimpleUserSerializer(friends, many=True).data

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = self.Meta.model(**validated_data)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['uid', 'username', 'first_name', 'last_name', 'avatar']
