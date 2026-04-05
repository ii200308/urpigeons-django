from django.apps import AppConfig


class RaceResultsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "race_results"

    def ready(self):
        from . import signals  # noqa
