from django.urls import path

from .views import (WebSocketTicketView, NotificationListView,
                    MarkNotificationReadView, MarkAllNotificationsAsReadView,
                    UserDeviceRegisterView)

urlpatterns = [
    path('notifications/tickets/', WebSocketTicketView.as_view(), name='websocket_tickets'),

    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/read/', MarkNotificationReadView.as_view(), name='read-notifications'),
    path('notifications/read-all/', MarkAllNotificationsAsReadView.as_view(), name='read-all-notifications'),

    path('devices/register/', UserDeviceRegisterView.as_view(), name='device-register'),

]
