from django.apps import AppConfig


class PhotoIndexConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "photoindex"
    verbose_name = "Path-backed photo index"
