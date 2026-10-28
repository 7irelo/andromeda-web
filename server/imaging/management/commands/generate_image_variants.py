from django.core.management.base import BaseCommand

from imaging import variants


class Command(BaseCommand):
    help = 'Create missing WebP variants for avatars and post images uploaded before variants existed.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Regenerate variants that already exist.')

    def handle(self, *args, force=False, **options):
        from posts.models import Post, PostMedia
        from users.models import User

        jobs = [
            (User.objects.exclude(avatar='').exclude(avatar__isnull=True), 'avatar', variants.AVATAR_WIDTHS),
            (Post.objects.exclude(image='').exclude(image__isnull=True), 'image', variants.POST_WIDTHS),
            (PostMedia.objects.filter(media_type='image'), 'file', variants.POST_WIDTHS),
        ]
        made = 0
        for qs, field, widths in jobs:
            for obj in qs.only('pk', field).iterator(chunk_size=500):
                f = getattr(obj, field)
                names = variants.variant_names(f.name, widths)
                if not names or (not force and all(f.storage.exists(n) for n in names)):
                    continue
                try:
                    made += len(variants.generate(f, widths))
                except Exception as exc:
                    self.stderr.write(f'{f.name}: {exc}')
        self.stdout.write(f'{made} variant(s) written.')
