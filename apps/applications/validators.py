from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^\+998\d{9}$',
    message="Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak."
)

telegram_validator = RegexValidator(
    regex=r'^https://[a-zA-Z0-9_]+\.t\.me$',
    message="Telegram havolasi https://username.t.me formatida bo'lishi kerak."
)

portfolio_validator = RegexValidator(
    regex=r'^https://.+$',
    message="Portfolio havolasi https:// bilan boshlanishi kerak."
)
