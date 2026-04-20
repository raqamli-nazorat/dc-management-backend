from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^\+998\d{9}$',
    message="Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak."
)

telegram_validator = RegexValidator(
    regex=r'^https://(t\.me/.+|[a-zA-Z0-9_]+\.t\.me)$',
    message="Telegram havolasi https://t.me/username yoki https://username.t.me formatida bo'lishi kerak."
)

portfolio_validator = RegexValidator(
    regex=r'^https://.+$',
    message="Portfolio havolasi https:// bilan boshlanishi kerak."
)


def validate_resume(file):
    if not file.name.endswith('.pdf'):
        raise ValidationError("Faqat PDF formatidagi fayl yuklanishi mumkin.")
    try:
        if file.size > 10 * 1024 * 1024:
            raise ValidationError("Fayl hajmi 10 MB dan oshmasligi kerak.")
    except (FileNotFoundError, OSError):
        pass
