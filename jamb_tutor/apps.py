from django.apps import AppConfig


def seed_subjects(sender, **kwargs):
    """Create the nine JAMB subjects after migrations. Safe to run repeatedly."""
    from django.db import DatabaseError

    from .constants import SUBJECTS
    from .models import Subject

    using = kwargs.get('using', 'default')
    try:
        for order, (name, slug, full_name, icon) in enumerate(SUBJECTS):
            Subject.objects.using(using).get_or_create(
                slug=slug,
                defaults={'name': name, 'full_name': full_name, 'icon': icon, 'sort_order': order},
            )
    except DatabaseError:
        pass  # tables don't exist yet (e.g. migrating a different app first)


class JambTutorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jamb_tutor'
    verbose_name = 'JAMB Tutor'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(seed_subjects, sender=self)
