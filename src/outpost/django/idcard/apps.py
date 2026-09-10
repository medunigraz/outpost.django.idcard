from django.apps import AppConfig


class IdcardConfig(AppConfig):
    # Pinned so the primary key type does not follow the host project's
    # DEFAULT_AUTO_FIELD. Without this, makemigrations produces a different
    # `id` column depending on which settings module it is run under, which is
    # where migration 0005's AlterField on `id` came from.
    default_auto_field = 'django.db.models.AutoField'
    name = 'outpost.django.idcard'
    verbose_name = 'Digital ID Cards'
