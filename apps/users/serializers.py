from django.contrib.auth import get_user_model
from django.db.models import Q, Count

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.projects.models import Status, ProjectStatus
from apps.users.models import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'role',
            'password', 'confirm_password',
            'fixed_salary', 'balance'
        )
        read_only_fields = ('id',)

    def validate(self, attrs):
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')

        if password is not None:
            if not password.isdigit():
                raise serializers.ValidationError({"password": "Parol faqat raqamlardan iborat bo'lishi kerak."})
            if password != confirm_password:
                raise serializers.ValidationError({"password": "Parollar mos kelmayapti. Qaytadan urinib ko'ring."})

        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password', None)
        password = validated_data.pop('password', None)

        user = User(**validated_data)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop('confirm_password', None)
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)
            instance.must_change_password = True

        instance.save()
        return instance


class UserShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'date_joined', 'role', 'is_active')


class ProfileSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'role', 'stats', 'fixed_salary', 'balance', 'date_joined', 'change_password', 'is_active')
        read_only_fields = ('id', 'username', 'role', 'fixed_salary', 'date_joined', 'change_password', 'is_active')

    def get_stats(self, obj):
        allowed_roles = [Role.MANAGER, Role.EMPLOYEE]

        if obj.role not in allowed_roles:
            return None

        all_projects = (
                obj.manager_projects.all() |
                obj.employee_projects.all()
        ).distinct()

        p_stats = all_projects.aggregate(
            total=Count('id'),
            planning=Count('id', filter=Q(status=ProjectStatus.PLANNING)),
            active=Count('id', filter=Q(status=ProjectStatus.ACTIVE)),
            completed=Count('id', filter=Q(status=ProjectStatus.COMPLETED)),
            cancelled=Count('id', filter=Q(status=ProjectStatus.CANCELLED)),
        )

        t_stats = obj.tasks.aggregate(
            total=Count('id'),
            todo=Count('id', filter=Q(status=Status.TODO)),
            in_progress=Count('id', filter=Q(status=Status.IN_PROGRESS)),
            done=Count('id', filter=Q(status=Status.DONE)),
            checked=Count('id', filter=Q(status=Status.CHECKED)),
            production=Count('id', filter=Q(status=Status.PRODUCTION))
        )

        return {
            "projects": {
                "total": p_stats['total'],
                "planning": p_stats['planning'],
                "active": p_stats['active'],
                "completed": p_stats['completed'],
                "cancelled": p_stats['cancelled'],
                "current_work": p_stats['planning'] + p_stats['active']
            },
            "tasks": {
                "total": t_stats['total'],
                "todo": t_stats['todo'],
                "in_progress": t_stats['in_progress'],
                "done": t_stats['done'],
                "checked": t_stats['checked'],
                "production": t_stats['production'],
                "overall_completed": t_stats['done'] + t_stats['checked'] + t_stats['production']
            }
        }


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Eski parol noto'g'ri.")
        return value

    def validate(self, attrs):
        new_password = attrs.get('new_password')
        confirm_new_password = attrs.get('confirm_new_password')
        old_password = attrs.get('old_password')

        if not new_password.isdigit():
            raise serializers.ValidationError({
                'new_password': "Parol faqat raqamlardan iborat bo'lishi kerak."
            })

        if new_password != confirm_new_password:
            raise serializers.ValidationError({
                'new_password': "Yangi parol maydonlari mos kelmadi."
            })

        if old_password == new_password:
            raise serializers.ValidationError({
                'new_password': "Yangi parol eskisidan farq qilishi kerak."
            })

        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.must_change_password = False
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data: dict = super().validate(attrs)
        user = self.user

        data["user"] = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "change_password": user.change_password,
            "is_active": user.is_active,
        }

        return data


class MyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data: dict = super().validate(attrs)

        refresh = RefreshToken(attrs["refresh"])
        user_id = refresh.get("user_id")

        try:
            user = User.objects.get(id=user_id)
            data["user"] = {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "change_password": user.change_password,
                "is_active": user.is_active,
            }
        except User.DoesNotExist:
            pass

        return data
