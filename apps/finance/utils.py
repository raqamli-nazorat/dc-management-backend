import re
from datetime import date, datetime, timedelta
from django.utils import timezone

MONTH_NAMES_MAP = {
    'yanvar': 1, 'fevral': 2, 'mart': 3, 'aprel': 4, 'may': 5, 'iyun': 6,
    'iyul': 7, 'avgust': 8, 'sentabr': 9, 'oktabr': 10, 'noyabr': 11, 'dekabr': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

MONTH_UZ_NAMES = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
    5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
    9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
}


def parse_month_input(val) -> date:
    if val is None:
        raise ValueError("Oy ko'rsatilmadi.")

    if isinstance(val, datetime):
        return val.date().replace(day=1)

    if isinstance(val, date):
        return val.replace(day=1)

    s = str(val).strip().lower()
    if not s:
        raise ValueError("Oy bo'sh bo'lishi mumkin emas.")

    for name, m_num in MONTH_NAMES_MAP.items():
        if name in s:
            year_match = re.search(r'\b(20\d\d|19\d\d)\b', s)
            if year_match:
                year = int(year_match.group(1))
                return date(year, m_num, 1)

    cleaned = re.sub(r'[\.\/]', '-', s)
    parts = cleaned.split('-')

    if len(parts) >= 2:
        p0, p1 = parts[0].strip(), parts[1].strip()
        if len(p0) == 4 and p0.isdigit() and p1.isdigit():
            year = int(p0)
            month = int(p1)
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return date(year, month, 1)

        if len(parts) == 2 and p1.isdigit() and len(p1) == 4 and p0.isdigit():
            month = int(p0)
            year = int(p1)
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return date(year, month, 1)

        if len(parts) == 3 and len(parts[2]) == 4 and parts[2].isdigit():
            month = int(parts[1])
            year = int(parts[2])
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return date(year, month, 1)

    raise ValueError(
        f"'{val}' noto'g'ri oy formati. Masalan: 2026-08 yoki 08.2026 ko'rinishida kiriting."
    )


def get_month_range(target=None):
    now = timezone.now()
    if target is None:
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_of_prev_month = first_of_this_month - timedelta(seconds=1)
        month_start = last_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = last_of_prev_month
        target_date = month_start.date()
    else:
        target_date = parse_month_input(target)
        year = target_date.year
        month = target_date.month

        tz = timezone.get_current_timezone()
        month_start = timezone.datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
        if month == 12:
            next_month_start = timezone.datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
        else:
            next_month_start = timezone.datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
        month_end = next_month_start - timedelta(microseconds=1)

    return month_start, month_end, target_date


def get_month_display_name(target_date: date) -> str:
    month_name = MONTH_UZ_NAMES.get(target_date.month, "")
    return f"{month_name} {target_date.year}"
