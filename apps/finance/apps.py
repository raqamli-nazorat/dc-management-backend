from django.apps import AppConfig


class FinanceConfig(AppConfig):
    name = 'apps.finance'
    verbose_name = 'Moliya bo\'limi'

    def ready(self):
        import apps.finance.signals
