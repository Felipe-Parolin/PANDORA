from rest_framework import serializers
from core.tax_ids import normalize_tax_id, valid_cnpj, valid_cpf
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    person_type_label = serializers.CharField(source="get_person_type_display", read_only=True)

    class Meta:
        model = Customer
        fields = "__all__"

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
        document = attrs.get("document", getattr(self.instance, "document", ""))
        person_type = attrs.get("person_type", getattr(self.instance, "person_type", None))
        expected = 11 if person_type == Customer.PersonType.INDIVIDUAL else 14
        if len(document) != expected:
            raise serializers.ValidationError({"document": f"Documento incompatível com o tipo de pessoa; esperado {expected} caracteres."})
        duplicates = Customer.objects.filter(document=document)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"document": "Já existe um cliente com este CPF/CNPJ."})
        return attrs
