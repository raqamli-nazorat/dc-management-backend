from rest_framework import serializers
from .models import AuditLog
from apps.users.serializers import UserShortSerializer


class AuditLogSerializer(serializers.ModelSerializer):
    user_info = UserShortSerializer(source='user', read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            'id', 'user_info', 'action', 'ip_address',
            'table_name', 'record_id', 'old_values', 'new_values',
            'created_at'
        )
