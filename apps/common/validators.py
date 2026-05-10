import os

from django.core.exceptions import ValidationError


def validate_only_pdf(value):
    ext = os.path.splitext(value.name)[1]
    if ext.lower() != '.pdf':
        raise ValidationError("Faqat PDF formatidagi fayl yuklanishi mumkin.")


def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1]

    valid_extensions = [
        '.jpg', '.jpeg', '.png', '.webp', '.gif',
        '.pdf', '.txt',
        '.doc', '.docx',
        '.xls', '.xlsx',
        '.ppt', '.pptx',
        '.csv'
    ]

    if not ext.lower() in valid_extensions:
        allowed_exts_str = ", ".join([e.replace('.', '').upper() for e in valid_extensions])
        raise ValidationError(
            f"Faqat quyidagi formatdagi fayllarni yuklash mumkin: {allowed_exts_str}."
        )


def validate_file_size(value):
    filesize = value.size

    if filesize > 10 * 1024 * 1024:
        raise ValidationError("Fayl hajmi 10 MB dan oshmasligi kerak!")
