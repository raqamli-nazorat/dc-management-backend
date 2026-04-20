from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'apps.notifications'
    verbose_name = 'Bildirishnomalar'

    def ready(self):
        import apps.notifications.signals
