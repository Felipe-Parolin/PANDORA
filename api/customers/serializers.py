import re
from rest_framework import serializers
from .models import Customer


def _valid_cpf(value):
    digits = [int(item) for item in value]
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for position in (9, 10):
        total = sum(digits[index] * (position + 1 - index) for index in range(position))
        remainder = total % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if digits[position] != expected:
            return False
    return True


def _valid_cnpj(value):
    digits = [int(item) for item in value]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for position, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        remainder = sum(digits[index] * weights[index] for index in range(position)) % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if digits[position] != expected:
            return False
    return True


class CustomerSerializer(serializers.ModelSerializer):
    person_type_label = serializers.CharField(source="get_person_type_display", read_only=True)

    class Meta:
        model = Customer
        fields = "__all__"

    def validate_document(self, value):
        digits = re.sub(r"\D", "", value)
        if len(digits) not in (11, 14):
            raise serializers.ValidationError("Informe um CPF com 11 dígitos ou CNPJ com 14 dígitos.")
        if len(digits) == 11 and not _valid_cpf(digits):
            raise serializers.ValidationError("CPF inválido.")
        if len(digits) == 14 and not _valid_cnpj(digits):
            raise serializers.ValidationError("CNPJ inválido.")
        return digits

    def validate(self, attrs):
        document = attrs.get("document", getattr(self.instance, "document", ""))
        person_type = attrs.get("person_type", getattr(self.instance, "person_type", None))
        expected = 11 if person_type == Customer.PersonType.INDIVIDUAL else 14
        if len(document) != expected:
            raise serializers.ValidationError({"document": f"Documento incompatível com o tipo de pessoa; esperado {expected} dígitos."})
        return attrs
