from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import UserShortSerializer
from .models import Todo

User = get_user_model()


class TodoSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)

    class Meta:
        model = Todo
        fields = ('id', 'user', 'user_info', 'title', 'is_done', 'created_at', 'updated_at', 'is_active')
        read_only_fields = ('id', 'user', 'created_at', 'updated_at')
