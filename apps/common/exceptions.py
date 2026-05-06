from django.http import JsonResponse
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as base_exception_handler
from rest_framework.response import Response
from rest_framework import status


def exception_handler(exc, context):
    response = base_exception_handler(exc, context)

    if response is None:
        return Response(
            {
                "data": None,
                "error": {
                    "errorId": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "isFriendly": False,
                    "errorMsg": "Serverdagi ichki xatolik.",
                    "details": None,
                },
                "success": False,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    error_msg = "Kutilmagan xatolik yuzaga keldi."
    details = None
    is_friendly = True

    if isinstance(exc, ValidationError) or response.status_code == status.HTTP_400_BAD_REQUEST:
        if isinstance(data, (dict, list)) and not (isinstance(data, dict) and "detail" in data):
            error_msg = "Ma'lumotlarni tekshirishda xatolik yuzaga keldi."
            details = data
        else:
            if isinstance(data, dict) and "detail" in data:
                error_msg = data["detail"]
            else:
                error_msg = "So'rov noto'g'ri."
    else:
        if isinstance(data, dict) and "detail" in data:
            error_msg = data["detail"]
        elif isinstance(data, dict):
            details = data
        elif isinstance(data, str):
            error_msg = data

    return Response(
        {
            "data": None,
            "error": {
                "errorId": response.status_code,
                "isFriendly": is_friendly,
                "errorMsg": str(error_msg),
                "details": details,
            },
            "success": False,
        },
        status=response.status_code,
    )


def handler404(request, exception, *args, **kwargs):
    return JsonResponse({
        "data": None,
        "error": {
            "errorId": status.HTTP_404_NOT_FOUND,
            "isFriendly": True,
            "errorMsg": "Sahifa topilmadi.",
        },
        "success": False
    }, status=status.HTTP_404_NOT_FOUND)


def handler500(request, *args, **kwargs):
    return JsonResponse({
        "data": None,
        "error": {
            "errorId": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "isFriendly": False,
            "errorMsg": "Serverdagi ichki xatolik.",
        },
        "success": False
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
