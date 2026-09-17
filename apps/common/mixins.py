import copy
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers, status


class SoftDeleteMixin:
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleBasedQuerySetMixin:
    full_access_roles = []

    def get_role_based_queryset(self, queryset, user):
        return queryset

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if not user or not user.is_authenticated:
            return queryset.none()

        if user.is_superuser or (
            self.full_access_roles and user.has_role(*self.full_access_roles)
        ):
            return queryset

        return self.get_role_based_queryset(queryset, user)


class TrashMixin:
    trash_user_field = "created_by"

    @extend_schema(request=None)
    @action(detail=False, methods=["get"])
    def trash(self, request):
        filter_kwargs = {self.trash_user_field: request.user}
        queryset = self.filter_queryset(self.get_queryset()).filter(**filter_kwargs)
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        filter_kwargs = {"pk": pk, self.trash_user_field: request.user}
        instance = self.get_queryset().filter(**filter_kwargs).first()

        if not instance:
            return Response(
                {"detail": "Ma'lumot topilmadi."}, status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, instance)

        if not getattr(instance, "is_deleted", False):
            return Response(
                {"detail": "Element chiqindi qutisida emas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.is_active = True
        instance.is_deleted = False
        instance.save()

        return Response({"detail": "Muvaffaqiyatli tiklandi."})

    @action(detail=True, methods=["delete"])
    def hard_delete(self, request, pk=None):
        filter_kwargs = {"pk": pk, self.trash_user_field: request.user}
        instance = self.get_queryset().filter(**filter_kwargs).first()

        if not instance:
            return Response(
                {"detail": "Ma'lumot topilmadi."}, status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, instance)

        if not getattr(instance, "is_deleted", False):
            return Response(
                {
                    "detail": "Faqat chiqindi qutisidagi elementlarni butunlay o'chirish mumkin."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.is_deleted = False
        instance.is_active = False
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ModelCleanMixin:
    def clean_model_instance(self, attrs):
        model_class = self.Meta.model
        request = self.context.get("request")
        user = getattr(request, "user", None)

        m2m_field_names = {f.name for f in model_class._meta.many_to_many}
        model_attrs = {k: v for k, v in attrs.items() if k not in m2m_field_names}

        if self.instance:
            instance = copy.deepcopy(self.instance)
            for attr, value in model_attrs.items():
                setattr(instance, attr, value)
        else:
            if "user" not in model_attrs and hasattr(model_class, "user") and user:
                model_attrs["user"] = user
            instance = model_class(**model_attrs)

        if user:
            instance._current_user = user

        try:
            instance.clean()
        except DjangoValidationError as exception:
            raise serializers.ValidationError(
                serializers.as_serializer_error(exception)
            )
        if self.instance:
            self.instance._skip_clean = True

        return instance

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self.clean_model_instance(attrs)
        return attrs

    def create(self, validated_data):
        model_class = self.Meta.model
        m2m_field_names = {f.name for f in model_class._meta.many_to_many}
        m2m_data = {}
        for field_name in list(validated_data.keys()):
            if field_name in m2m_field_names:
                m2m_data[field_name] = validated_data.pop(field_name)

        instance = model_class(**validated_data)
        instance._skip_clean = True
        instance.save()

        for field_name, value in m2m_data.items():
            getattr(instance, field_name).set(value)

        return instance
