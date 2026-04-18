from django.utils import timezone
from rest_framework import serializers

from apps.applications.models import Region, District, Direction, Application, ApplicationStatus


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ('id', 'name', 'is_application', 'is_active')
        read_only_fields = ('id',)


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ('id', 'region', 'name', 'is_application', 'is_active')
        read_only_fields = ('id',)


class DirectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Direction
        fields = ('id', 'name', 'is_application', 'is_active')
        read_only_fields = ('id',)


class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = ('id', 'full_name', 'birth_date', 'is_student', 'university', 'region', 'district',
                  'phone', 'telegram', 'direction', 'resume', 'extra_info', 'portfolio', 'status', 'is_active'
                  )
        read_only_fields = ('id', 'status', 'is_active')

    def validate(self, attrs):
        if attrs.get('is_student') and not attrs.get('university'):
            raise serializers.ValidationError({
                'university': "Talaba bo'lsangiz o'qish joyi va kursingizni kiritishingiz shart!"
            })
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
