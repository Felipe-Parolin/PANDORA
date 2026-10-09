from datetime import timedelta

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
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
from maintenance.services import generate_due_preventive_orders, maintenance_alert_status, plan_due_date


class PatternTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tech@example.com", "strong-password", full_name="Técnico", role=User.Role.MAINTENANCE)
        category = EquipmentCategory.objects.create(name="Teste", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Marca", model="M1", serial_number="SER-1", internal_code="EQ-T1", daily_rate=100)

    def test_builder_creates_and_resets_order(self):
        builder = ServiceOrderBuilder().equipment(self.equipment).responsible(self.user).report("Falha no motor").kind(ServiceOrder.Type.CORRECTIVE)
        order = builder.build()
        self.assertEqual(order.equipment, self.equipment)
        self.assertTrue(order.number.startswith(f"OS-{timezone.localdate().year}-"))
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


class PeriodicMaintenanceTests(TestCase):
    def setUp(self):
        self.technician = User.objects.create_user(
            "periodic@example.com", "strong-password", full_name="Técnico", role=User.Role.MAINTENANCE
        )
        category = EquipmentCategory.objects.create(name="Periódico", default_daily_rate=100)
        self.equipment = Equipment.objects.create(
            category=category, name="Compactador", brand="Marca", model="M1",
            serial_number="PER-1", internal_code="PER-1", daily_rate=100,
        )

    def test_first_due_date_uses_registration_date_when_no_date_was_given(self):
        plan = MaintenancePlan.objects.create(
            equipment=self.equipment, name="Revisão mensal", maintenance_type=MaintenancePlan.Type.PREVENTIVE,
            interval_days=30,
        )
        self.assertEqual(plan_due_date(plan), timezone.localdate() + timedelta(days=30))
        self.assertEqual(generate_due_preventive_orders(), [])

    def test_due_plan_creates_one_scheduled_order_and_next_cycle_after_completion(self):
        today = timezone.localdate()
        plan = MaintenancePlan.objects.create(
            equipment=self.equipment, name="Revisão semanal", maintenance_type=MaintenancePlan.Type.PREVENTIVE,
            interval_days=7, next_due_date=today, criticality=MaintenancePlan.Criticality.HIGH,
        )
        created = generate_due_preventive_orders()
        self.assertEqual(len(created), 1)
        order = created[0]
        self.assertEqual(order.maintenance_type, ServiceOrder.Type.PREVENTIVE)
        self.assertEqual(order.status, ServiceOrder.Status.SCHEDULED)
        self.assertEqual(order.plan_due_date, today)
        self.assertEqual(order.scheduled_at.date(), today)
        self.assertEqual(order.priority, "ALTA")
        self.assertIsNone(order.opened_by)
        self.assertIn("Revisão semanal", order.symptoms)
        self.assertEqual(generate_due_preventive_orders(), [])
        self.assertEqual(plan.service_orders.count(), 1)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.status, Equipment.Status.MAINTENANCE)

        client = APIClient()
        client.force_authenticate(self.technician)
        self.assertEqual(client.delete(f"/api/service-orders/{order.pk}/").status_code, 409)
        response = client.patch(
            f"/api/service-orders/{order.pk}/", {"status": ServiceOrder.Status.COMPLETED}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["plan_name"], plan.name)
        plan.refresh_from_db()
        self.assertEqual(plan.last_service_date, today)
        self.assertEqual(plan.next_due_date, today + timedelta(days=7))
        self.assertEqual(generate_due_preventive_orders(), [])
        next_orders = generate_due_preventive_orders(today=today + timedelta(days=7))
        self.assertEqual(len(next_orders), 1)
        self.assertEqual(next_orders[0].plan_due_date, today + timedelta(days=7))

    def test_sync_endpoint_is_idempotent_and_requires_manage_permission(self):
        plan = MaintenancePlan.objects.create(
            equipment=self.equipment, name="Revisão hoje", maintenance_type=MaintenancePlan.Type.PREVENTIVE,
            interval_days=10, next_due_date=timezone.localdate(),
        )
        client = APIClient()
        client.force_authenticate(self.technician)
        first = client.post("/api/maintenance-plans/sync-due/")
        second = client.post("/api/maintenance-plans/sync-due/")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data["created"], 1)
        self.assertEqual(second.data["created"], 0)
        self.assertEqual(plan.service_orders.count(), 1)
        seller = User.objects.create_user(
            "seller-periodic@example.com", "strong-password", full_name="Vendedor", role=User.Role.SALES
        )
        client.force_authenticate(seller)
        denied = client.post("/api/maintenance-plans/sync-due/")
        self.assertEqual(denied.status_code, 403)

    def test_inactive_or_rental_plan_does_not_generate_periodic_order(self):
        for maintenance_type, active in ((MaintenancePlan.Type.PREVENTIVE, False), (MaintenancePlan.Type.PRE_RENTAL, True)):
            MaintenancePlan.objects.create(
                equipment=self.equipment, name="Não recorrente", maintenance_type=maintenance_type,
                interval_days=7, next_due_date=timezone.localdate(), active=active,
            )
        self.assertEqual(generate_due_preventive_orders(), [])
