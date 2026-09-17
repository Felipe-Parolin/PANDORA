from django.test import TestCase
from django.core.exceptions import ValidationError

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from maintenance.models import ServiceOrder
from maintenance.patterns import (
    CorrectiveMaintenanceFactory,
    MaintenanceKitFactory,
    PreventiveChecklist,
    PreventiveMaintenanceFactory,
    ReportProcessorFactory,
    ServiceOrderBuilder,
    ServiceOrderOpeningDirector,
    TextReportProcessorCreator,
)


class PatternTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tech@example.com", "strong-password", full_name="Técnico", role=User.Role.MAINTENANCE)
        category = EquipmentCategory.objects.create(name="Teste", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Marca", model="M1", serial_number="SER-1", internal_code="EQ-T1", daily_rate=100)

    def test_builder_creates_and_resets_order(self):
        builder = ServiceOrderBuilder().equipment(self.equipment).responsible(self.user).report("Falha no motor").kind(ServiceOrder.Type.CORRECTIVE)
        order = builder.build()
        self.assertEqual(order.equipment, self.equipment)
        with self.assertRaises(ValueError):
            builder.build()

    def test_director_coordinates_builder_steps(self):
        order = ServiceOrderOpeningDirector().open(
            equipment=self.equipment,
            opened_by=self.user,
            symptoms="Vazamento de óleo",
            maintenance_type=ServiceOrder.Type.CORRECTIVE,
        )
        self.assertEqual(order.symptoms, "Vazamento de óleo")

    def test_factories_select_products(self):
        self.assertEqual(ReportProcessorFactory.create("text").process("  texto   limpo "), "texto limpo")
        self.assertIsInstance(ReportProcessorFactory.creator("text"), TextReportProcessorCreator)
        kit = MaintenanceKitFactory.create(ServiceOrder.Type.PREVENTIVE)
        self.assertIn("Lubrificação", kit.checklist)
        self.assertIsInstance(PreventiveMaintenanceFactory().create_checklist(), PreventiveChecklist)
        self.assertNotEqual(
            PreventiveMaintenanceFactory().create_route().steps(),
            CorrectiveMaintenanceFactory().create_route().steps(),
        )

    def test_abandoned_order_requires_reason_and_tracks_transition(self):
        order = ServiceOrder.objects.create(
            equipment=self.equipment,
            opened_by=self.user,
            technician=self.user,
            symptoms="Falha intermitente",
            maintenance_type=ServiceOrder.Type.CORRECTIVE,
            status=ServiceOrder.Status.OPEN,
        )
        order.status = ServiceOrder.Status.ABANDONED
        with self.assertRaises(ValidationError):
            order.full_clean()
        order.abandoned_reason = "Peça especial indisponível; chamado deve ser redistribuído."
        order.full_clean()
        order.save()
        self.assertIsNotNone(order.abandoned_at)
        self.assertIsNone(order.closed_at)
        self.assertFalse(order.released)

    def test_in_progress_order_tracks_start(self):
        order = ServiceOrder.objects.create(
            equipment=self.equipment,
            opened_by=self.user,
            technician=self.user,
            symptoms="Ruído no conjunto",
            maintenance_type=ServiceOrder.Type.CORRECTIVE,
            status=ServiceOrder.Status.IN_PROGRESS,
        )
        self.assertIsNotNone(order.started_at)
