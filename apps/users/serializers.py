from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.applications.models import Region, District, Position
from apps.applications.serializers import RegionSerializer, DistrictSerializer, PositionSerializer
from apps.users.models import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    region_info = RegionSerializer(source='region', read_only=True)
    district_info = DistrictSerializer(source='district', read_only=True)
    position_info = PositionSerializer(source='position', read_only=True)

    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all(), write_only=True)
    district = serializers.PrimaryKeyRelatedField(queryset=District.objects.all(), write_only=True)
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all(), required=False, write_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'avatar', 'username', 'phone_number', 'card_number', 'region', 'region_info', 'district',
            'district_info', 'position', 'position_info',
            'passport_series', 'passport_image', 'social_links', 'roles',
            'password', 'confirm_password',
            'fixed_salary', 'balance'
        )
        read_only_fields = ('id', 'balance')
        extra_kwargs = {
            'username': {'validators': []}
        }

    def validate_username(self, value):
        instance = self.instance

        if instance and instance.username == value:
            return value

        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bu username allaqachon band. Iltimos, boshqasini tanlang.")

        return value

    def validate(self, attrs):
        request = self.context.get('request')
        current_user = request.user

        input_roles = attrs.get('roles', [])
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')

        if current_user.has_role(Role.ADMIN) and not current_user.has_role(Role.SUPERADMIN):
            if Role.SUPERADMIN in input_roles:
                raise serializers.ValidationError({
                    "roles": "Siz Super Admin yarata olmaysiz."
                })

            if self.instance and self.instance.has_role(Role.SUPERADMIN):
                raise serializers.ValidationError({
                    "detail": "Super Admin ma'lumotlarini o'zgartirish huquqi sizda yo'q."
                })

        if password is not None:
            if not password.isdigit():
                raise serializers.ValidationError({"password": "Parol faqat raqamlardan iborat bo'lishi kerak."})
            if password != confirm_password:
                raise serializers.ValidationError({"password": "Parollar mos kelmayapti."})

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
            instance.change_password = True

        instance.save()
        return instance


class UserShortSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source='region.name', read_only=True, default=None)
    district = serializers.CharField(source='district.name', read_only=True, default=None)
    position = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ('id', 'avatar', 'username', 'phone_number', 'card_number',
                  'region', 'district', 'position', 'roles', 'date_joined')


class ProfileSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source='region.name', read_only=True, default=None)
    district = serializers.CharField(source='district.name', read_only=True, default=None)
    position = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ('id', 'avatar', 'username', 'phone_number', 'card_number',
                  'passport_series', 'passport_image', 'region', 'district',
                  'position', 'roles', 'fixed_salary', 'balance', 'social_links',
                  'date_joined', 'change_password')


class SocialLinksSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('social_links',)


class CardNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('card_number',)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        min_length=4,
        error_messages={
            'min_length': "Parol kamida 4 ta raqamdan iborat bo'lishi kerak."
        })

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
        user.change_password = False
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data: dict = super().validate(attrs)
        user = self.user

        data["user"] = {
            "id": user.id,
            "avatar": user.avatar.url if user.avatar else None,
            "username": user.username,
            "phone_number": user.phone_number,
            "region": user.region.name if user.region else None,
            "district": user.district.name if user.district else None,
            "position": user.position.name if user.position else None,
            "roles": user.roles,
            "date_joined": user.date_joined,
            "change_password": user.change_password,
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
                "avatar": user.avatar.url if user.avatar else None,
                "username": user.username,
                "phone_number": user.phone_number,
                "region": user.region.name if user.region else None,
                "district": user.district.name if user.district else None,
                "position": user.position.name if user.position else None,
                "roles": user.roles,
                "date_joined": user.date_joined,
                "change_password": user.change_password,
            }
        except User.DoesNotExist:
            pass

        return data
