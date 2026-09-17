from django.db.models.deletion import ProtectedError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ProtectedError):
        return Response(
            {"detail": "Este registro possui vínculos e não pode ser excluído. Inative-o ou remova primeiro os registros dependentes."},
            status=409,
        )
    return None
