import re

from rest_framework import serializers
from core.tax_ids import normalize_tax_id, valid_cnpj, valid_cpf
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    person_type_label = serializers.CharField(source="get_person_type_display", read_only=True)
    # O tamanho válido e a unicidade são verificados após remover a formatação.
    document = serializers.CharField()
    address_cep = serializers.CharField(required=False, allow_blank=True, max_length=9)

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ("marketing_unsubscribe_token",)

    def validate_address_cep(self, value):
        if not value:
            return ""
        if not re.fullmatch(r"\d{5}-?\d{3}", value):
            raise serializers.ValidationError("Informe um CEP com 8 dígitos.")
        return value.replace("-", "")

    def validate_address_number(self, value):
        return value.strip()

    def validate_document(self, value):
        digits = normalize_tax_id(value)
        if len(digits) not in (11, 14):
            raise serializers.ValidationError("Informe um CPF com 11 dígitos ou CNPJ com 14 caracteres.")
        if len(digits) == 11 and not valid_cpf(digits):
            raise serializers.ValidationError("CPF inválido.")
        if len(digits) == 14 and not valid_cnpj(digits):
            raise serializers.ValidationError("CNPJ inválido.")
        return digits

    def validate(self, attrs):
        document = normalize_tax_id(attrs.get("document", getattr(self.instance, "document", "")))
        person_type = attrs.get("person_type", getattr(self.instance, "person_type", None))
        expected = 11 if person_type == Customer.PersonType.INDIVIDUAL else 14
        validator = valid_cpf if expected == 11 else valid_cnpj
        if not validator(document):
            label = "CPF" if expected == 11 else "CNPJ"
            raise serializers.ValidationError({"document": f"Informe um {label} válido para este tipo de pessoa."})
        duplicates = Customer.objects.filter(document__iexact=document)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"document": "Já existe um cliente com este CPF/CNPJ."})
        return attrs
