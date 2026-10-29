import re

from rest_framework import serializers

from core.tax_ids import normalize_tax_id, valid_cnpj
from .models import FiscalCompany, FiscalCustomerData, FiscalEquipmentData


BRAZIL_STATES = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


class FiscalAddressSerializer(serializers.ModelSerializer):
    def validate_postal_code(self, value):
        value = value.replace("-", "").strip()
        if value and not re.fullmatch(r"[0-9]{8}", value):
            raise serializers.ValidationError("Informe um CEP de 8 dígitos.")
        return value

    def validate_state(self, value):
        value = value.upper().strip()
        if value and value not in BRAZIL_STATES:
            raise serializers.ValidationError("Informe uma UF brasileira válida.")
        return value

    def validate_municipality_code(self, value):
        if value and not re.fullmatch(r"[0-9]{7}", value):
            raise serializers.ValidationError("O código IBGE do município deve ter 7 dígitos.")
        return value


class FiscalCompanySerializer(FiscalAddressSerializer):
    cnpj = serializers.CharField(max_length=18, allow_blank=True, required=False)
    postal_code = serializers.CharField(max_length=9, allow_blank=True, required=False)

    class Meta:
        model = FiscalCompany
        exclude = ("id",)
        read_only_fields = ("updated_at",)

    def validate_cnpj(self, value):
        value = normalize_tax_id(value)
        if value and not valid_cnpj(value):
            raise serializers.ValidationError("CNPJ inválido. Confira os caracteres e os dígitos verificadores.")
        return value

    def validate_cnae(self, value):
        if value and not re.fullmatch(r"[0-9]{7}", value):
            raise serializers.ValidationError("Informe o CNAE com 7 dígitos, sem pontuação.")
        return value


class FiscalCustomerDataSerializer(FiscalAddressSerializer):
    postal_code = serializers.CharField(max_length=9, allow_blank=True, required=False)

    class Meta:
        model = FiscalCustomerData
        exclude = ("id", "customer")
        read_only_fields = ("updated_at",)


class FiscalEquipmentDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalEquipmentData
        exclude = ("id", "equipment")
        read_only_fields = ("updated_at",)

    def validate_ncm(self, value):
        if value and not re.fullmatch(r"[0-9]{8}", value):
            raise serializers.ValidationError("Informe um NCM de 8 dígitos, sem pontuação.")
        return value

    def validate_asset_value(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Informe um valor do bem maior que zero.")
        return value
