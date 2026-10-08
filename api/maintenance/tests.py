from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from maintenance.models import MaintenancePlan, ServiceOrder
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
from maintenance.services import maintenance_alert_status


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

    def test_service_order_identification_is_fixed_after_opening(self):
        other = Equipment.objects.create(
            category=self.equipment.category, name="Outro equipamento", brand="Marca", model="M2",
            serial_number="SER-2", internal_code="EQ-T2", daily_rate=100,
        )
        order = ServiceOrder.objects.create(
            equipment=self.equipment, opened_by=self.user, symptoms="Falha original",
            maintenance_type=ServiceOrder.Type.CORRECTIVE,
        )
        client = APIClient()
        client.force_authenticate(self.user)
        for field, value in (
            ("equipment", other.pk),
            ("maintenance_type", ServiceOrder.Type.PREVENTIVE),
            ("symptoms", "Relato substituído"),
        ):
            response = client.patch(f"/api/service-orders/{order.pk}/", {field: value}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn(field, response.data)
        order.refresh_from_db()
        self.assertEqual(order.equipment, self.equipment)
        self.assertEqual(order.maintenance_type, ServiceOrder.Type.CORRECTIVE)
        self.assertEqual(order.symptoms, "Falha original")
        response = client.patch(f"/api/service-orders/{order.pk}/", {"priority": "ALTA"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.priority, "ALTA")


class MaintenanceAlertTests(TestCase):
    def test_critical_usage_limit_triggers_alert(self):
        category = EquipmentCategory.objects.create(name="Horas", default_daily_rate=100)
        equipment = Equipment.objects.create(
            category=category,
            name="Equipamento por uso",
            brand="Marca",
            model="M1",
            serial_number="USAGE-1",
            internal_code="USE-1",
            daily_rate=100,
            current_usage_hours=120,
        )
        plan = MaintenancePlan.objects.create(
            equipment=equipment,
            name="Revisão 100 horas",
            maintenance_type=MaintenancePlan.Type.PREVENTIVE,
            usage_limit=100,
            last_service_usage_hours=0,
            criticality=MaintenancePlan.Criticality.CRITICAL,
        )
        self.assertEqual(maintenance_alert_status(plan), "CRITICAL")
