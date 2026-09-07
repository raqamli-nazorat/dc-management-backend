from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.finance.tasks import calculate_monthly_salaries
from apps.finance.utils import parse_month_input, get_month_display_name, get_month_range

User = get_user_model()


class Command(BaseCommand):
    help = "Ko'rsatilgan oy uchun barcha xodimlar va menejerlarning oylik maoshlarini hisoblash"

    def add_arguments(self, parser):
        parser.add_argument(
            'month',
            nargs='?',
            type=str,
            default=None,
            help="Hisoblanishi kerak bo'lgan oy (masalan: 2026-08, 08.2026 yoki 'avgust 2026')"
        )
        parser.add_argument(
            '-m', '--month-opt',
            dest='month_opt',
            type=str,
            default=None,
            help="Hisoblanishi kerak bo'lgan oy (nomlangan argument sifatida)"
        )
        parser.add_argument(
            '-u', '--user',
            dest='user',
            type=str,
            default=None,
            help="Faqat bitta foydalanuvchi uchun hisoblash (ID yoki username)"
        )
        parser.add_argument(
            '--no-notify',
            dest='no_notify',
            action='store_true',
            default=False,
            help="Hisobchilarga bildirishnoma yuborilmasin"
        )

    def handle(self, *args, **options):
        month_raw = options.get('month') or options.get('month_opt')

        if not month_raw:
            try:
                self.stdout.write(self.style.WARNING("Oy ko'rsatilmadi."))
                month_input = input("Hisoblanadigan oyni kiriting (masalan: 2026-08, o'tgan oyni olish uchun bo'sh qoldiring): ").strip()
                if month_input:
                    month_raw = month_input
            except (EOFError, KeyboardInterrupt):
                month_raw = None

        try:
            _, _, target_date = get_month_range(month_raw)
        except ValueError as e:
            raise CommandError(str(e))

        month_str = target_date.strftime("%Y-%m")
        display_name = get_month_display_name(target_date)

        user_id = None
        user_arg = options.get('user')
        if user_arg:
            if user_arg.isdigit():
                user_obj = User.objects.filter(id=int(user_arg)).first()
            else:
                user_obj = User.objects.filter(username=user_arg).first()

            if not user_obj:
                raise CommandError(f"'{user_arg}' foydalanuvchisi topilmadi!")
            user_id = user_obj.id

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING(f"  OYLIK MAOSHLARNI HISOBLASH: {display_name} ({month_str})"))
        if user_id:
            self.stdout.write(self.style.NOTICE(f"  Tanlangan foydalanuvchi: {user_obj.username} (ID: {user_obj.id})"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

        notify_accountants = not options.get('no_notify')

        stats = calculate_monthly_salaries(
            target_month=target_date,
            user_id=user_id,
            notify_accountants=notify_accountants
        )

        for detail in stats.get("details", []):
            u = detail["user"]
            st = detail["status"]

            if st == "confirmed":
                payroll = detail["payroll"]
                self.stdout.write(
                    self.style.NOTICE(
                        f" [!] {u.username:<20} | Jami: {payroll.total_amount:>12,.2f} so'm | Allaqachon tasdiqlangan (O'tkazildi)"
                    )
                )
            elif st == "error":
                err = detail.get("error", "Noma'lum xatolik")
                self.stdout.write(
                    self.style.ERROR(
                        f" [X] {u.username:<20} | Xatolik: {err}"
                    )
                )
            else:
                payroll = detail["payroll"]
                tag = "Yangi" if st == "created" else "Yangilandi"
                self.stdout.write(
                    self.style.SUCCESS(
                        f" [+] {u.username:<20} | Asosiy: {payroll.fixed_salary:>11,.2f} | "
                        f"KPI: {payroll.kpi_bonus:>10,.2f} | "
                        f"Jarima: {payroll.penalty_amount:>10,.2f} | "
                        f"Jami: {payroll.total_amount:>12,.2f} so'm ({tag})"
                    )
                )

        self.stdout.write(self.style.MIGRATE_HEADING("-" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("  NATIJA:"))
        self.stdout.write(f"  - Jami hisoblangan foydalanuvchilar: {stats['processed']}")
        self.stdout.write(self.style.SUCCESS(f"  - Yangi yaratilgan:                  {stats['created']}"))
        self.stdout.write(self.style.SUCCESS(f"  - Yangilangan:                       {stats['updated']}"))
        if stats['skipped_confirmed'] > 0:
            self.stdout.write(self.style.NOTICE(f"  - Tasdiqlangan (o'tkazilgan):        {stats['skipped_confirmed']}"))
        if stats['errors'] > 0:
            self.stdout.write(self.style.ERROR(f"  - Xatoliklar:                        {stats['errors']}"))
        self.stdout.write(self.style.SUCCESS(f"  - Jami hisoblangan summa:            {stats['total_amount']:,.2f} so'm"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

        if stats['errors'] == 0:
            self.stdout.write(self.style.SUCCESS("Muvaffaqiyatli yakunlandi!"))
        else:
            self.stdout.write(self.style.WARNING("Hisob-kitob yakunlandi, lekin ayrim xatoliklar yuz berdi."))
