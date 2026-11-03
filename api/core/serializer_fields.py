from rest_framework import serializers


class OptionalDateTimeField(serializers.DateTimeField):
    """Formulários HTML representam a ausência de data por texto vazio."""

    def run_validation(self, data=serializers.empty):
        if data == "":
            data = None
        return super().run_validation(data)
