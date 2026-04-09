from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = 'apps.audit'
    verbose_name = 'Tarix bo\'limi'

    def ready(self):
        import apps.audit.signals
