from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.applications.models import Region, District, Position, Application, ApplicationStatus


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ('id', 'name', 'is_application', 'created_at')
        read_only_fields = ('id', 'created_at')


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ('id', 'region', 'name', 'created_at')
        read_only_fields = ('id', 'created_at')


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ('id', 'name', 'is_application', 'created_at')
        read_only_fields = ('id', 'created_at')


class ApplicationSerializer(serializers.ModelSerializer):
    region_info = RegionSerializer(source='region', read_only=True)
    position_info = PositionSerializer(source='position', read_only=True)

    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all(), write_only=True)
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all(), write_only=True)

    class Meta:
        model = Application
        fields = ('id', 'full_name', 'birth_date', 'is_student', 'university', 'region', 'region_info',
                  'phone', 'telegram', 'position', 'position_info', 'resume', 'extra_info', 'portfolio',
                  'status', 'reviewed_by', 'conclusion', 'reviewed_at', 'created_at'
                  )
        read_only_fields = ('id', 'status', 'reviewed_by', 'conclusion', 'reviewed_at', 'created_at')

    def __init__(self, *args, **kwargs):
        super(ApplicationSerializer, self).__init__(*args, **kwargs)
        from apps.users.serializers import UserShortSerializer
        self.fields['reviewed_by'] = UserShortSerializer(read_only=True)

    def validate(self, attrs):
        if self.instance:
            instance = self.instance
            for attr, value in attrs.items():
                setattr(instance, attr, value)
        else:
            instance = Application(**attrs)

        try:
            instance.clean()
        except DjangoValidationError as e:
            if hasattr(e, 'message_dict'):
                raise serializers.ValidationError(e.message_dict)
            else:
                raise serializers.ValidationError({"detail": e.messages})

        return attrs


class ApplicationStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = (
            'status',
            'conclusion',
        )

    def validate_conclusion(self, value):
        if value and not value.strip():
            raise serializers.ValidationError("Xulosa bo'sh bo'lishi mumkin emas!")
        return value

    def validate(self, attrs):
        status = attrs.get('status')
        conclusion = attrs.get('conclusion')

        if status in [ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED]:
            if not conclusion or not conclusion.strip():
                raise serializers.ValidationError({
                    'conclusion': "Qaror qabul qilishda xulosa kiritish shart!"
                })
        return attrs

    def update(self, instance, validated_data):
        instance.status = validated_data.get('status', instance.status)
        instance.conclusion = validated_data.get('conclusion', instance.conclusion)
        instance.reviewed_by = self.context['request'].user
        instance.reviewed_at = timezone.now()
        instance.save()
        return instance
