from django.core.management.base import BaseCommand

from maintenance.services import generate_due_preventive_orders


class Command(BaseCommand):
    help = "Gera uma OS preventiva agendada para cada plano periódico vencido. Seguro para execução diária."

    def handle(self, *args, **options):
        orders = generate_due_preventive_orders()
        self.stdout.write(self.style.SUCCESS(f"{len(orders)} OS preventiva(s) gerada(s)."))
