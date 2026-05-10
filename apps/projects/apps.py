from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = 'apps.projects'
    verbose_name = 'Loyihalar bo\'limi'

    def ready(self):
        import apps.projects.signals
