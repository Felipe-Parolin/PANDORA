from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from accounts.permissions import ACLPermission
from core.models import AuditLog
from maintenance.models import ServiceOrder
from rentals.models import RentalInspection, RentalQuote
from rentals.services import availability_reason

from .services import task_items
from .models import TransportTask, Vehicle
from .serializers import TransportTaskSerializer, VehicleSerializer


class VehicleViewSet(ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    permission_classes = [ACLPermission]
    acl_view = "logistics.view"
    acl_manage = "logistics.manage"

    def destroy(self, request, *args, **kwargs):
        if self.get_object().transport_tasks.exists():
            return Response({"detail": "O veículo possui histórico de viagens e não pode ser excluído. Inative-o."}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)


class TransportTaskViewSet(ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = TransportTask.objects.select_related("quote__customer", "vehicle", "driver", "created_by").prefetch_related("rental_items__equipment", "quote__items__equipment")
    serializer_class = TransportTaskSerializer
    permission_classes = [ACLPermission]
    acl_view = "logistics.view"
    acl_manage = "logistics.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        for key, field in (("quote", "quote_id"), ("status", "status"), ("leg", "leg"), ("vehicle", "vehicle_id"), ("driver", "driver_id")):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{field: value})
        date_start, date_end = self.request.query_params.get("start_date"), self.request.query_params.get("end_date")
        if date_start: queryset = queryset.filter(scheduled_at__date__gte=date_start)
        if date_end: queryset = queryset.filter(scheduled_at__date__lte=date_end)
        time_start, time_end = self.request.query_params.get("start_time"), self.request.query_params.get("end_time")
        if time_start: queryset = queryset.filter(scheduled_at__time__gte=time_start)
        if time_end: queryset = queryset.filter(scheduled_at__time__lte=time_end)
        city = self.request.query_params.get("city")
        if city: queryset = queryset.filter(address__icontains=city)
        customer = self.request.query_params.get("customer")
        if customer:
            queryset = queryset.filter(quote__customer_id=customer) if str(customer).isdigit() else queryset.filter(quote__customer__name__icontains=customer)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(quote__number__icontains=search) | Q(quote__customer__name__icontains=search) | Q(vehicle__plate__icontains=search) | Q(address__icontains=search))
        return queryset

    @action(detail=False, methods=["get"], url_path="agenda")
    def agenda(self, request):
        from datetime import date, timedelta
        from rest_framework.exceptions import ValidationError
        try:
            start = date.fromisoformat(request.query_params.get("start", ""))
            end = date.fromisoformat(request.query_params.get("end", ""))
        except ValueError:
            raise ValidationError({"period": "Informe start e end no formato AAAA-MM-DD."})
        if end < start or (end - start).days > 366:
            raise ValidationError({"period": "O período deve ser válido e ter no máximo 366 dias."})
        tasks = self.get_queryset().filter(scheduled_at__date__gte=start, scheduled_at__date__lte=end).exclude(status=TransportTask.Status.CANCELLED)
        return Response({"start": start, "end": end, "count": tasks.count(), "results": self.get_serializer(tasks, many=True).data})

    def _day_param(self, request):
        from datetime import date
        raw = request.query_params.get("date")
        try:
            return date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            raise ValidationError({"date": "Informe a data no formato AAAA-MM-DD."})

    @action(detail=False, methods=["get"], url_path="day-plan")
    def day_plan(self, request):
        """Entregas e retiradas do dia, por período (manhã/tarde) e veículo, com peso e coordenadas para o mapa."""
        from .dayplan import build_day_plan
        day = self._day_param(request)
        can_phone = request.user.has_acl("customers.view") or request.user.has_acl("customers.manage")
        geocode = request.query_params.get("geocode", "1") not in ("0", "false")
        return Response(build_day_plan(self.get_queryset(), day, can_view_phone=can_phone, geocode=geocode))

    @action(detail=False, methods=["get"], url_path="day-plan-pdf")
    def day_plan_pdf(self, request):
        from django.http import HttpResponse
        from .dayplan import build_day_plan
        from .dayplan_pdf import build_day_plan_pdf
        day = self._day_param(request)
        can_phone = request.user.has_acl("customers.view") or request.user.has_acl("customers.manage")
        plan = build_day_plan(self.get_queryset(), day, can_view_phone=can_phone, geocode=False)
        response = HttpResponse(build_day_plan_pdf(plan, day), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="horario-entregas-{day.isoformat()}.pdf"'
        return response

    @action(detail=True, methods=["get"], url_path="loading-order")
    def loading_order(self, request, pk=None):
        from io import BytesIO
        from django.conf import settings
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ReportLabImage
        from xml.sax.saxutils import escape
        import qrcode
        task = self.get_object()
        quote = task.quote
        can_view_customer_phone = request.user.has_acl("customers.view") or request.user.has_acl("customers.manage")
        grouped_tasks = TransportTask.objects.filter(
            trip_reference=task.trip_reference, vehicle=task.vehicle, driver=task.driver,
            scheduled_at=task.scheduled_at, leg=task.leg,
        ).select_related("quote__customer").order_by("load_sequence", "scheduled_at", "pk") if task.trip_reference else TransportTask.objects.filter(pk=task.pk)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Company", parent=styles["Title"], alignment=TA_CENTER, fontSize=15, leading=18))
        story = [Paragraph("MAZZI DEPÓSITO E MATERIAIS DE CONSTRUÇÃO", styles["Company"]),
                 Paragraph("ORDEM DE CARREGAMENTO", styles["Heading1"]), Spacer(1, 5*mm)]
        details = [
            ["Ordem", f"TR-{task.pk:06d}", "Operação", task.get_leg_display()],
            ["Data/hora", task.scheduled_at.strftime("%d/%m/%Y %H:%M") if task.scheduled_at else "Não agendada", "Viagem", task.trip_reference or "—"],
            ["Veículo", str(task.vehicle) if task.vehicle else "Não definido", "Placa", task.vehicle.plate if task.vehicle else "—"],
            ["Motorista", task.driver.full_name if task.driver else "Não definido", "Situação", task.get_status_display()],
            ["Cliente", quote.customer.name, "Orçamento", quote.number],
            ["Contato", (quote.customer.phone or "Não informado") if can_view_customer_phone else "Restrito por permissão", "", ""],
            ["Sequência da parada", str(task.load_sequence), "Referência", task.trip_reference or "—"],
            ["Destino", task.address, "Complemento", task.complement or "—"],
        ]
        table = Table(details, colWidths=[24*mm, 62*mm, 24*mm, 62*mm])
        table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .4, colors.grey), ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke), ("BACKGROUND", (2,0), (2,-1), colors.whitesmoke), ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"), ("VALIGN", (0,0), (-1,-1), "TOP"), ("FONTSIZE", (0,0), (-1,-1), 8), ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5)]))
        story += [table, Spacer(1, 7*mm), Paragraph("EQUIPAMENTOS PARA CONFERÊNCIA E CARREGAMENTO", styles["Heading2"])]
        rows = [["Seq.", "Cliente", "Código", "Equipamento / identificação", "Qtd.", "QR / conferência"]]
        sequence = 1
        load_order = {}
        for stop in grouped_tasks:
            for code in stop.load_manifest or []:
                if code not in load_order:
                    load_order[code] = len(load_order)
        load_lines = [(stop, line) for stop in grouped_tasks for line in task_items(stop)]
        load_lines.sort(key=lambda pair: (load_order.get(pair[1].equipment.internal_code.upper(), 999999), pair[0].load_sequence, pair[1].equipment.internal_code))
        for stop, line in load_lines:
                equipment = line.equipment
                target = f"{settings.FRONTEND_URL.rstrip('/')}/equipamentos?qr={equipment.qr_code_token}"
                qr_buffer = BytesIO()
                qrcode.make(target).save(qr_buffer, format="PNG")
                qr_buffer.seek(0)
                qr_image = ReportLabImage(qr_buffer, width=14*mm, height=14*mm)
                rows.append([str(sequence), stop.quote.customer.name, equipment.internal_code,
                             f"{equipment.name} · {equipment.brand} {equipment.model} · Série {equipment.serial_number}\n{line.start_date:%d/%m/%Y} a {line.end_date:%d/%m/%Y}",
                             "1", qr_image])
                sequence += 1
        items_table = Table(rows, repeatRows=1, colWidths=[10*mm, 32*mm, 20*mm, 76*mm, 10*mm, 24*mm])
        items_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#243447")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.grey), ("FONTSIZE", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.whitesmoke])]))
        stop_summary = "<br/>".join(escape(f"{stop.load_sequence}. {stop.quote.customer.name} · {stop.address}" + (f" · {stop.quote.customer.phone}" if can_view_customer_phone and stop.quote.customer.phone else "")) for stop in grouped_tasks)
        story += [items_table, Spacer(1, 8*mm), Paragraph("Paradas desta viagem", styles["Heading2"]), Paragraph(stop_summary or "—", styles["BodyText"]), Spacer(1, 4*mm), Paragraph("Período da locação: " + quote.start_date.strftime("%d/%m/%Y") + " a " + quote.end_date.strftime("%d/%m/%Y"), styles["BodyText"]), Spacer(1, 3*mm), Paragraph("Observações: " + escape(task.notes or quote.notes or "—"), styles["BodyText"]), Spacer(1, 16*mm),
                  Paragraph("Responsável pela conferência: __________________________________________", styles["BodyText"]), Spacer(1, 10*mm),
                  Paragraph("Assinatura: __________________________________________________________", styles["BodyText"])]
        doc.build(story)
        from django.http import HttpResponse
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="ordem-carregamento-{task.pk}.pdf"'
        return response

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        snapshot = self.get_object()
        def task_group(task):
            return TransportTask.objects.filter(
                trip_reference=task.trip_reference, vehicle_id=task.vehicle_id, driver_id=task.driver_id,
                scheduled_at=task.scheduled_at, leg=task.leg, status__in=("PLANNED", "IN_TRANSIT"),
            ) if task.trip_reference else TransportTask.objects.filter(pk=task.pk)
        quote_ids = set(task_group(snapshot).values_list("quote_id", flat=True)) | {snapshot.quote_id}
        # A prorrogação e o planejamento também bloqueiam primeiro a locação.
        locked_quotes = {quote.pk: quote for quote in RentalQuote.objects.select_for_update().filter(pk__in=quote_ids).order_by("pk")}
        task = TransportTask.objects.select_for_update().get(pk=snapshot.pk)
        if task.status != TransportTask.Status.PLANNED:
            raise ValidationError({"status": "Somente viagens planejadas podem ser iniciadas."})
        if not task.vehicle_id or not task.driver_id or not task.scheduled_at:
            raise ValidationError("Defina veículo, motorista e horário antes da saída.")
        vehicle = Vehicle.objects.select_for_update().get(pk=task.vehicle_id)
        grouped = task_group(task)
        if not set(grouped.values_list("quote_id", flat=True)).issubset(locked_quotes):
            raise ValidationError({"schedule": "O agrupamento mudou durante a saída. Atualize as viagens e tente novamente."})
        if vehicle.status != Vehicle.Status.AVAILABLE or TransportTask.objects.filter(
            vehicle=vehicle, status=TransportTask.Status.IN_TRANSIT
        ).exclude(pk=task.pk).exclude(pk__in=grouped.values("pk")).exists():
            raise ValidationError({"vehicle": "Veículo indisponível ou em outra viagem."})
        if not task.driver.is_active:
            raise ValidationError({"driver": "O motorista precisa estar ativo."})
        from datetime import timedelta
        from django.db.models import Q
        start_at = task.scheduled_at
        end_at = task.scheduled_end_at or (start_at + timedelta(hours=2))
        overlap = Q(scheduled_end_at__gt=start_at) | Q(scheduled_end_at__isnull=True, scheduled_at__gt=start_at - timedelta(hours=2))
        vehicle_conflicts = TransportTask.objects.select_for_update().filter(
            vehicle=vehicle, status__in=(TransportTask.Status.PLANNED, TransportTask.Status.IN_TRANSIT),
            scheduled_at__lt=end_at,
        ).filter(overlap).exclude(pk=task.pk).exclude(pk__in=grouped.values("pk"))
        driver_conflicts = TransportTask.objects.select_for_update().filter(
            driver=task.driver, status__in=(TransportTask.Status.PLANNED, TransportTask.Status.IN_TRANSIT),
            scheduled_at__lt=end_at,
        ).filter(overlap).exclude(pk=task.pk).exclude(pk__in=grouped.values("pk"))
        vehicle_conflict = vehicle_conflicts.exists()
        driver_conflict = driver_conflicts.exists()
        if vehicle_conflict or driver_conflict:
            raise ValidationError({"schedule": "Veículo ou motorista possui outra viagem em horário incompatível."})
        group_tasks = list(grouped.select_related("quote__customer").prefetch_related("quote__items__equipment", "rental_items__equipment"))
        if not group_tasks:
            group_tasks = [task]
        group_quotes = [locked_quotes[item.quote_id] for item in group_tasks]
        from .services import task_items
        from assets.models import Equipment
        equipment_ids = {line.equipment_id for stop in group_tasks for line in task_items(stop)}
        list(Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk"))
        lines_by_id = {}
        for group_task, group_quote in zip(group_tasks, group_quotes):
            selected = list(task_items(group_task))
            stages = {"PENDING"} if task.leg == "DELIVERY" else {"DELIVERED"}
            allowed_statuses = {"APPROVED", "ACTIVE"} if task.leg == "DELIVERY" else {"ACTIVE"}
            if not selected or group_quote.status not in allowed_statuses or any(line.stage not in stages for line in selected):
                raise ValidationError({"quote": "Uma das viagens contém equipamentos fora da etapa operacional correta."})
            lines_by_id.update({line.pk: line for line in selected})
            if task.leg == "DELIVERY":
                ids = [line.equipment_id for line in selected]
                inspections = list(group_quote.inspections.filter(inspection_type="PRE_RENTAL", equipment_id__in=ids))
                if len(inspections) != len(selected) or any(inspection.result not in {"APPROVED", "APPROVED_WITH_NOTES"} or inspection.critical_impediment or not ServiceOrder.objects.filter(rental_inspection=inspection, status="COMPLETED", released=True).exists() for inspection in inspections):
                    raise ValidationError({"inspections": f"A viagem de {group_quote.number} possui itens sem liberação técnica."})
                conflicts = {line.equipment.internal_code: reason for line in selected if (reason := availability_reason(line.equipment, line.start_date, line.end_date, group_quote))}
                from rentals.models import RentalItem
                if RentalItem.objects.filter(equipment_id__in=ids, stage="DELIVERED", quote__status="ACTIVE").exclude(quote=group_quote).exists():
                    raise ValidationError({"availability": "Um equipamento ainda não retornou de outra locação."})
                if conflicts:
                    raise ValidationError({"availability": conflicts})
        lines = list(lines_by_id.values())
        if vehicle.capacity_kg is None:
            raise ValidationError({"vehicle": "Cadastre a capacidade de carga do veículo antes de iniciar a viagem."})
        missing_weights = [line.equipment.internal_code for line in lines if line.equipment.estimated_weight_kg is None]
        if missing_weights:
            raise ValidationError({"load": f"Informe o peso estimado (kg) dos equipamentos: {', '.join(missing_weights)}."})
        total_weight = sum((line.equipment.estimated_weight_kg for line in lines), 0)
        if total_weight > vehicle.capacity_kg:
            raise ValidationError({"load": f"Carga agrupada estimada de {total_weight} kg excede a capacidade de {vehicle.capacity_kg} kg do veículo."})
        quote = next(item for item in group_quotes if item.pk == task.quote_id)
        task.status = TransportTask.Status.IN_TRANSIT
        task.departed_at = timezone.now()
        task.save(update_fields=("status", "departed_at"))
        AuditLog.objects.create(user=request.user, entity="TransportTask", record_id=str(task.pk), action="STARTED", data={"quote": quote.number, "leg": task.leg})
        return Response(self.get_serializer(task).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        task = TransportTask.objects.select_for_update().get(pk=self.get_object().pk)
        if task.status != TransportTask.Status.IN_TRANSIT:
            raise ValidationError({"status": "Somente viagens em transporte podem ser concluídas."})
        task.status = TransportTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=("status", "completed_at"))
        AuditLog.objects.create(user=request.user, entity="TransportTask", record_id=str(task.pk), action="COMPLETED", data={"quote": task.quote.number, "leg": task.leg})
        return Response(self.get_serializer(task).data)
