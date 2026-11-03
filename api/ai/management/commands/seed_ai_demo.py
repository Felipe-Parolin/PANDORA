from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from core.models import Notification
from ai.demo_pdf import build_pdf, wrap
from assets.models import Equipment, MediaAsset
from maintenance.models import MaintenanceActivity, ServiceOrder

MANUALS = {
    "EQ-003": ("Manual demonstrativo · Betoneira elétrica", [
        ("Partida e alimentação", "Se a betoneira não liga, confirme primeiro a tomada, o disjuntor e o cabo de alimentação. Verifique o capacitor de partida: capacitor com falha causa zumbido sem rotação do tambor. Desligue e desconecte da energia antes de abrir a tampa do motor."),
        ("Rotação e transmissão", "Ruído metálico e perda de rotação indicam desgaste da coroa ou da cremalheira. Lubrifique a coroa a cada 50 horas de uso e confira o alinhamento do pinhão. Folga excessiva exige troca do conjunto coroa e pinhão."),
    ]),
    "EQ-005": ("Manual demonstrativo · Gerador diesel", [
        ("Oscilação de tensão", "Oscilação de tensão após aquecer costuma indicar regulador de tensão (AVR) fora da faixa ou conexões soltas no painel. Meça a tensão em vazio e com carga e inspecione os bornes do alternador."),
        ("Partida", "Dificuldade de partida: verifique bateria, nível de combustível, filtro de combustível e sangria do sistema. Troque o filtro a cada 250 horas."),
    ]),
    "EQ-004": ("Manual demonstrativo · Martelete rompedor", [
        ("Perda de impacto", "Perda de impacto com motor funcionando indica desgaste das escovas de carvão, do pistão ou falta de graxa no mecanismo de percussão. Substitua escovas abaixo de 6 mm e relubrifique o mecanismo."),
        ("Superaquecimento", "Aquecimento excessivo: limpe as entradas de ventilação e respeite pausas de trabalho. Verifique o isolamento do cabo antes de cada locação."),
    ]),
    "EQ-001": ("Manual demonstrativo · Compactador de solo", [
        ("Vibração fraca", "Vibração fraca pode indicar óleo hidráulico baixo, correia frouxa ou excêntrico desgastado. Confira o nível de óleo e a tensão da correia a cada 40 horas de uso."),
    ]),
    "EQ-002": ("Manual demonstrativo · Cortadora de piso", [
        ("Disco e refrigeração", "Disco que trava ou aquece: confirme a água de refrigeração, o aperto da flange e o desgaste do segmento diamantado. Nunca opere sem a proteção do disco."),
    ]),
    "EQ-006": ("Manual demonstrativo · Andaime tubular", [
        ("Montagem e rodízios", "Confira travas dos rodízios, soldas das travessas e encaixe das plataformas antes de cada entrega. Rodízio com folga deve ser substituído."),
    ]),
}

# (código, sintomas, diagnóstico, peças, testes finais, prioridade, dias atrás)
HISTORY = (
    ("EQ-003", "Betoneira não liga, motor apenas zumbe.", "Capacitor de partida com falha.", "Capacitor de partida 40 µF", "Partida e rotação do tambor sob carga.", "ALTA", 120),
    ("EQ-003", "Betoneira não liga após troca de tomada; disjuntor desarma.", "Cabo de alimentação com isolamento danificado.", "Cabo PP 3x2,5 mm", "Teste de isolamento e partida.", "ALTA", 70),
    ("EQ-003", "Tambor trava e faz ruído metálico ao girar.", "Coroa desgastada, folga no pinhão.", "Conjunto coroa e pinhão", "Rotação por 15 minutos sem ruído.", "NORMAL", 25),
    ("EQ-005", "Gerador oscila a tensão após aquecer.", "Regulador de tensão (AVR) fora da faixa.", "Regulador de tensão AVR", "Tensão estável em vazio e com carga.", "ALTA", 95),
    ("EQ-005", "Gerador com dificuldade de partida a frio.", "Filtro de combustível saturado e ar no sistema.", "Filtro de combustível", "Partida a frio em 3 tentativas.", "NORMAL", 40),
    ("EQ-004", "Martelete perde impacto depois de alguns minutos.", "Escovas de carvão desgastadas.", "Jogo de escovas de carvão", "Teste de impacto contínuo por 10 minutos.", "NORMAL", 60),
    ("EQ-001", "Compactador com vibração fraca.", "Correia frouxa e óleo hidráulico baixo.", "Correia e óleo hidráulico", "Vibração dentro do padrão.", "NORMAL", 50),
)


class Command(BaseCommand):
    help = "Cria histórico técnico e manuais PDF fictícios para demonstrar a IA (idempotente)."

    def handle(self, *args, **options):
        admin = User.objects.filter(is_superuser=True).first() or User.objects.filter(role=User.Role.ADMIN).first()
        technician = User.objects.filter(role=User.Role.MAINTENANCE).first() or admin
        equipment = {e.internal_code: e for e in Equipment.objects.all()}
        if not equipment or admin is None:
            raise CommandError("Execute antes `seed_demo` ou `seed_realistic_demo` para criar usuários e equipamentos.")
        manuals = orders = 0
        for code, (title, sections) in MANUALS.items():
            item = equipment.get(code)
            if item is None or MediaAsset.objects.filter(equipment=item, name=title).exists():
                continue
            pages = [[title.upper(), "Documento fictício gerado para a demonstração do PANDORA.", ""] +
                     [line for heading, body in sections[i:i + 1] for line in (heading, *wrap(body), "")] for i in range(len(sections))]
            media = MediaAsset(name=title, category=MediaAsset.Category.MANUAL, description="Manual demonstrativo para a consulta assistida por IA.",
                               equipment=item, uploaded_by=admin)
            media.file.save(f"{code.lower()}-manual-demo.pdf", ContentFile(build_pdf(pages)), save=True)  # o sinal indexa o PDF
            manuals += 1
        for code, symptoms, diagnosis, parts, tests, priority, days in HISTORY:
            item = equipment.get(code)
            if item is None or ServiceOrder.objects.filter(equipment=item, symptoms=symptoms).exists():
                continue
            order = ServiceOrder.objects.create(
                equipment=item, maintenance_type=ServiceOrder.Type.CORRECTIVE, status=ServiceOrder.Status.COMPLETED, priority=priority,
                symptoms=symptoms, diagnosis=diagnosis, parts_used=parts, final_tests=tests, released=True, labor_hours=1.5,
                opened_by=admin, technician=technician,
            )
            opened = timezone.now() - timedelta(days=days)
            ServiceOrder.objects.filter(pk=order.pk).update(opened_at=opened, closed_at=opened + timedelta(days=2))
            Notification.objects.filter(event_key__startswith=f"order:{order.pk}:").delete()  # histórico antigo não gera avisos
            MaintenanceActivity.objects.create(service_order=order, description=f"Executado reparo: {diagnosis}", hours=1.5, part_used=parts, completed=True)
            orders += 1
        self.stdout.write(self.style.SUCCESS(f"{manuals} manual(is) e {orders} OS históricas criados para a demonstração da IA."))
