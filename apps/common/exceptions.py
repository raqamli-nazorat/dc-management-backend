import logging

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import JsonResponse

from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as base_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger("api.errors")

SERVER_ERROR_MSG = "Serverdagi ichki xatolik."


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = _convert_django_validation_error(exc)

    response = base_exception_handler(exc, context)

    if response is not None:
        if isinstance(response.data, dict):
            response.data.setdefault("_error_code", _extract_error_code(exc))
        return response

    if settings.DEBUG:
        return None

    request = context.get("request")
    logger.error(
        "Unhandled API exception: %s %s",
        getattr(request, "method", "-"),
        getattr(request, "path", "-"),
        exc_info=exc,
    )

    set_rollback()

    return Response(
        {
            "detail": SERVER_ERROR_MSG,
            "_is_friendly": False,
            "_error_code": "server_error",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _convert_django_validation_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(detail=exc.message_dict)
    return DRFValidationError(detail=exc.messages)


def _extract_error_code(exc):
    code = getattr(exc, "default_code", None)
    return str(code) if code else "error"


def _error_response(status_code, message, error_code, is_friendly=True):
    return JsonResponse(
        {
            "data": None,
            "error": {
                "errorId": status_code,
                "errorCode": error_code,
                "isFriendly": is_friendly,
                "errorMsg": message,
                "details": None,
            },
            "success": False,
        },
        status=status_code,
        json_dumps_params={"ensure_ascii": False},
    )


def handler400(request, exception=None, *args, **kwargs):
    return _error_response(
        status.HTTP_400_BAD_REQUEST,
        "Noto'g'ri so'rov.",
        "bad_request",
    )


def handler403(request, exception=None, *args, **kwargs):
    return _error_response(
        status.HTTP_403_FORBIDDEN,
        "Ushbu amal uchun ruxsat yo'q.",
        "permission_denied",
    )


def handler404(request, exception=None, *args, **kwargs):
    return _error_response(
        status.HTTP_404_NOT_FOUND,
        "Sahifa topilmadi.",
        "not_found",
    )


def handler500(request, *args, **kwargs):
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        SERVER_ERROR_MSG,
        "server_error",
        is_friendly=False,
    )