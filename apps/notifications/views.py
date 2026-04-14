import uuid

from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status, permissions
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from .serializers import NotificationSerializer, UserDeviceSerializer
from .models import Notification, UserDevice


@extend_schema(tags=["Notifications"])
class WebSocketTicketView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ticket = str(uuid.uuid4())
        cache.set(f"ws_ticket_{ticket}", request.user.id, timeout=60)

        return Response({
            "ticket": ticket,
            "expires_in": 60
        })


@extend_schema(tags=["Notifications"])
class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['type', 'is_read']

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('is_read')


@extend_schema(tags=["Notifications"])
class MarkNotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        update_rows = Notification.objects.filter(
            pk=pk,
            user=self.request.user,
            is_read=False
        ).update(is_read=True)

        if update_rows:
            return Response({"message": "Xabar o'qildi deb belgilandi."}, status=status.HTTP_200_OK)

        return Response(
            {"detail": "Xabar topilmadi yoki allaqachon o'qilgan."},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(tags=["Notifications"])
class MarkAllNotificationsAsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        updated_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        return Response({
            "message": f"{updated_count} ta xabar muvaffaqiyatli o'qildi.",
        })


@extend_schema(tags=['Register User Device'], request=UserDeviceSerializer)
class UserDeviceRegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserDeviceSerializer

    def post(self, request, *args, **kwargs):
        serializer = UserDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['fcm_token']
        device_type = serializer.validated_data['device_type']

        device, created = UserDevice.objects.update_or_create(
            fcm_token=token,
            defaults={
                'user': request.user,
                'device_type': device_type
            }
        )

        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            {"message": "Qurilma muvaffaqiyatli ro'yxatdan o'tkazildi"},
            status=status_code
        )
