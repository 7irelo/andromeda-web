from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'name', 'surname', 'avatar', 'bio', 'email', 'password']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        # Extract password from validated_data
        password = validated_data.pop('password', None)
        # Create a new instance of the user without saving it to the database yet
        instance = self.Meta.model(**validated_data)
        if password is not None:
            # Set the password for the instance
            instance.set_password(password)
        # Save the instance to the database
        instance.save()
        return instance
