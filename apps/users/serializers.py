from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db.models import Q, Count

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.projects.models import Status, ProjectStatus
from apps.users.models import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=6)
    confirm_password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'phone_number', 'first_name',
            'last_name', 'role', 'password', 'confirm_password',
            'fixed_salary',
        )
        read_only_fields = ('id',)

    def validate(self, attrs):
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')

        if password is not None:
            if password != confirm_password:
                raise serializers.ValidationError({"password": "The passwords did not match."})

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

        instance.save()
        return instance


class ProfileSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'phone_number', 'first_name', 'last_name',
                  'role', 'stats', 'fixed_salary', 'date_joined')
        read_only_fields = ('id', 'role', 'fixed_salary', 'date_joined')

    def get_stats(self, obj):
        allowed_roles = [Role.MANAGER, Role.EMPLOYEE, Role.AUDITOR]

        if obj.role not in allowed_roles:
            return None

        all_projects = (
                obj.manager_projects.all() |
                obj.employee_projects.all() |
                obj.audited_projects.all()
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
    old_password = serializers.CharField(min_length=8, max_length=128, write_only=True,
                                         style={'input_type': 'password'})
    new_password = serializers.CharField(min_length=8, max_length=128, write_only=True,
                                         style={'input_type': 'password'})
    confirm_new_password = serializers.CharField(min_length=8, max_length=128, write_only=True,
                                                 style={'input_type': 'password'})

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("The old password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({
                'password': "The new password fields did not match."
            })
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({
                'password': "The new password must be different from the old one."
            })

        try:
            validate_password(attrs['new_password'], user=self.context['request'].user)
        except ValidationError as e:
            raise serializers.ValidationError({'password': e.messages})

        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data: dict = super().validate(attrs)

        user = self.user

        data["user"] = {
            "id": user.id,
            "username": user.username,
            "phone_number": user.phone_number,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
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
                "phone_number": user.phone_number,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
            }
        except User.DoesNotExist:
            pass

        return data


class PinSetSerializer(serializers.Serializer):
    pin = serializers.CharField(
        min_length=4,
        max_length=4,
        write_only=True,
    )

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("The PIN must consist only of numbers!")
        return value


class PinCheckSerializer(serializers.Serializer):
    pin = serializers.CharField(min_length=4, max_length=4, write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        pin = attrs.get('pin')

        if not user.pin_code:
            raise serializers.ValidationError({
                "pin": "PIN has not been set yet. Please set a PIN first."
            })

        if not check_password(pin, user.pin_code):
            raise serializers.ValidationError({
                "pin": "The entered PIN code is incorrect!"
            })

        return attrs
