from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = 'apps.audit'

    def ready(self):
        import apps.audit.signals
