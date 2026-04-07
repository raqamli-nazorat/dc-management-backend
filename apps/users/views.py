from drf_spectacular.utils import extend_schema
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rest_framework import viewsets, permissions, generics, filters, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .permissions import IsSuperAdmin
from .serializers import (UserSerializer, ProfileSerializer, ChangePasswordSerializer,
                          MyTokenRefreshSerializer, MyTokenObtainPairSerializer,
                          PinSetSerializer, PinCheckSerializer)

User = get_user_model()


@extend_schema(tags=['Users'], summary="SuperAdmin")
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsSuperAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'first_name', 'last_name']


@extend_schema(tags=['Profile'])
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Profile"])
class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['put']

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Profile"])
class SetPinView(generics.GenericAPIView):
    serializer_class = PinSetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pin = serializer.validated_data['pin']
        request.user.pin_code = make_password(pin)
        request.user.save()

        return Response({
            'message': "PIN successfully saved."
        }, status=status.HTTP_200_OK)


@extend_schema(tags=["Profile"])
class CheckPinView(generics.GenericAPIView):
    serializer_class = PinCheckSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        return Response({
            "id": user.id,
            "username": user.username,
            "phone_number": user.phone_number,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
        })


@extend_schema(tags=["Authorization"])
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@extend_schema(tags=["Authorization"])
class MyTokenRefreshView(TokenRefreshView):
    serializer_class = MyTokenRefreshSerializer
