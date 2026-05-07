import os

from django.core.exceptions import ValidationError


def validate_only_pdf(value):
    ext = os.path.splitext(value.name)[1]
    if ext.lower() != '.pdf':
        raise ValidationError("Faqat PDF formatidagi fayl yuklanishi mumkin.")


def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1]

    valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.webp']

    if not ext.lower() in valid_extensions:
        raise ValidationError(
            "Faqat PDF, JPG, JPEG, PNG yoki WEBP formatidagi fayllarni yuklash mumkin."
        )


def validate_file_size(value):
    filesize = value.size

    if filesize > 10 * 1024 * 1024:
        raise ValidationError("Fayl hajmi 10 MB dan oshmasligi kerak!")
