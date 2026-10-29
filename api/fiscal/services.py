"""Provider-neutral preparation data. Never signs or transmits a fiscal document."""

from django.utils import timezone

from core.tax_ids import normalize_tax_id, valid_cnpj, valid_cpf
from .models import FiscalCompany, FiscalCustomerData, FiscalEquipmentData, ICMSTaxpayer
from .serializers import FiscalCompanySerializer, FiscalCustomerDataSerializer, FiscalEquipmentDataSerializer


ADDRESS_FIELDS = {
    "postal_code": "CEP", "street": "logradouro", "number": "número (ou S/N)",
    "neighborhood": "bairro", "city": "município", "state": "UF",
    "municipality_code": "código IBGE do município",
}
INTEGRATION_PENDING = [
    "Definir e integrar o emissor fiscal e suas credenciais em homologação.",
    "Validar com a contabilidade o documento de cobrança e as regras de remessa/retorno, CFOP e IBS/CBS aplicáveis.",
    "Homologar autorização, rejeição, consulta, cancelamento e guarda dos arquivos fiscais antes da produção.",
]


def company_data():
    return FiscalCompany.objects.filter(pk=1).first() or FiscalCompany(pk=1)


def prepare_rental(quote):
    company = company_data()
    customer = quote.customer
    recipient = FiscalCustomerData.objects.filter(customer=customer).first() or FiscalCustomerData(customer=customer)
    issues = []

    def missing(group, entity_id, obj, fields):
        for field, label in fields.items():
            if not getattr(obj, field, None):
                issues.append({"group": group, "entity_id": entity_id, "field": field, "message": f"Informe {label}."})

    missing("company", 1, company, {"legal_name": "a razão social", "cnpj": "o CNPJ", "cnae": "o CNAE", **ADDRESS_FIELDS})
    if company.cnpj and not valid_cnpj(normalize_tax_id(company.cnpj)):
        issues.append({"group": "company", "entity_id": 1, "field": "cnpj", "message": "Confira o CNPJ do emitente."})
    if company.tax_regime == FiscalCompany.TaxRegime.UNKNOWN:
        issues.append({"group": "company", "entity_id": 1, "field": "tax_regime", "message": "Confirme o regime tributário."})
    for group, entity_id, obj in (("company", 1, company), ("customer", customer.id, recipient)):
        if obj.icms_status == ICMSTaxpayer.UNKNOWN:
            issues.append({"group": group, "entity_id": entity_id, "field": "icms_status", "message": "Confirme a situação de contribuinte do ICMS."})
        elif obj.icms_status == ICMSTaxpayer.CONTRIBUTOR and not obj.state_registration:
            issues.append({"group": group, "entity_id": entity_id, "field": "state_registration", "message": "Informe a inscrição estadual do contribuinte."})
    missing("customer", customer.id, recipient, ADDRESS_FIELDS)
    document = normalize_tax_id(customer.document)
    if not (valid_cpf(document) if customer.person_type == "PF" else valid_cnpj(document)):
        issues.append({"group": "customer", "entity_id": customer.id, "field": "document", "message": "Corrija o CPF/CNPJ no cadastro do cliente."})
    if not customer.is_active:
        issues.append({"group": "customer", "entity_id": customer.id, "field": "is_active", "message": "O cliente está inativo; revise seu cadastro."})
    equipment_data = []
    lines = list(quote.items.select_related("equipment"))
    profiles = {item.equipment_id: item for item in FiscalEquipmentData.objects.filter(equipment_id__in=[line.equipment_id for line in lines])}
    for line in lines:
        equipment = line.equipment
        profile = profiles.get(equipment.id) or FiscalEquipmentData(equipment=equipment)
        missing("equipment", equipment.id, profile, {"ncm": "o NCM do equipamento"})
        if profile.asset_value is None:
            issues.append({"group": "equipment", "entity_id": equipment.id, "field": "asset_value", "message": "Informe o valor do bem para preparar a remessa/retorno; não é a diária."})
        equipment_data.append({
            "id": equipment.id, "code": equipment.internal_code, "name": equipment.name,
            "serial_number": equipment.serial_number, "fiscal": FiscalEquipmentDataSerializer(profile).data,
            "daily_rate": str(line.daily_rate), "days": line.quantity_days, "rental_total": str(line.total),
        })
    if not lines:
        issues.append({"group": "rental", "entity_id": quote.id, "field": "items", "message": "A locação precisa ter equipamentos."})
    return {
        "format": "pandora-fiscal-preparation-v1", "generated_at": timezone.now(),
        "fiscal_document": False, "can_issue": False, "taxes_calculated": False,
        "data_ready": not issues, "issues": issues, "integration_pending": INTEGRATION_PENDING,
        "company": FiscalCompanySerializer(company).data,
        "customer": {"id": customer.id, "name": customer.name, "person_type": customer.person_type,
                     "document": document, "email": customer.email, "phone": customer.phone,
                     "legacy_address": customer.address, "fiscal": FiscalCustomerDataSerializer(recipient).data},
        "rental": {"id": quote.id, "number": quote.number, "status": quote.status,
                   "start_date": quote.start_date, "end_date": quote.end_date,
                   "commercial_totals": {"equipment": str(quote.subtotal), "transport": str(quote.transport_fee),
                                         "discount": str(quote.discount), "total": str(quote.total)},
                   "delivery_address": quote.delivery_address, "delivery_complement": quote.delivery_complement,
                   "return_address": quote.return_address, "return_complement": quote.return_complement},
        "equipment": equipment_data,
    }
