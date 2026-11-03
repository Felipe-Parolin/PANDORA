from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exporta os dados do sistema em JSON portável (RNF8). Para backup completo use também pg_dump e a pasta media/."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="pandora-export.json", help="Arquivo de saída (padrão: pandora-export.json).")

    def handle(self, *args, **options):
        call_command(
            "dumpdata", natural_foreign=True, natural_primary=True, indent=2, output=options["output"],
            exclude=["contenttypes", "auth.permission", "sessions", "admin.logentry"],
        )
        self.stdout.write(self.style.SUCCESS(f"Dados exportados para {options['output']}. O arquivo contém dados pessoais: guarde-o com segurança."))
