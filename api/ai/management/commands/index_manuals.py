from django.core.management.base import BaseCommand

from ai.knowledge import INDEXABLE_CATEGORIES, index_media, is_indexable
from assets.models import MediaAsset


class Command(BaseCommand):
    help = "Indexa (ou reindexa) manuais e documentos PDF para a consulta assistida por IA."

    def add_arguments(self, parser):
        parser.add_argument("--equipment", type=int, help="Limita a um equipamento (id).")

    def handle(self, *args, **options):
        queryset = MediaAsset.objects.filter(category__in=INDEXABLE_CATEGORIES)
        if options["equipment"]:
            queryset = queryset.filter(equipment_id=options["equipment"])
        total = 0
        for media in queryset:
            if is_indexable(media):
                index = index_media(media)
                total += 1
                self.stdout.write(f"{media.name}: {index.get_status_display()} ({index.chunk_count} trechos)")
        self.stdout.write(self.style.SUCCESS(f"{total} arquivo(s) processado(s)."))
