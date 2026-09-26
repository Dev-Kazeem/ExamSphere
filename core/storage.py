from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """
    Same as Django's manifest storage (cache-busted hashed filenames), but a
    broken reference inside a third-party package's bundled CSS (e.g.
    django-jazzmin's AdminLTE assets pointing at a .css.map file that isn't
    shipped) doesn't abort the entire collectstatic run.
    """
    manifest_strict = False

    def post_process(self, *args, **kwargs):
        for name, hashed_name, processed in super().post_process(*args, **kwargs):
            if isinstance(processed, Exception):
                continue
            yield name, hashed_name, processed