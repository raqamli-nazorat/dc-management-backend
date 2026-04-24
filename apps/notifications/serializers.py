from rest_framework import serializers

from .models import Notification, UserDevice


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            'id',
            'title',
            'message',
            'type',
            'extra_data',
            'is_read',
            'created_at'
        )


class UserDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = ('fcm_token', 'device_type', 'device_id')
