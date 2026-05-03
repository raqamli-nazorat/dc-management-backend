import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.finance.models import Payroll
from apps.notifications.models import Notification, NotificationType
from apps.projects.models import MeetingAttendance, Project, ProjectStatus, Task, TaskStatus
from apps.users.models import Role, User

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _get_month_range(now):
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_of_prev_month = first_of_this_month - timedelta(seconds=1)
    first_of_prev_month = last_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first_of_prev_month, last_of_prev_month


def _send_accountant_notifications(month_label):
    accountants = User.objects.filter(
        roles__contains=[Role.ACCOUNTANT],
        is_active=True
    ).only('id')

    notifications = [
        Notification(
            user=accountant,
            title="Oylik hisob-kitob yakunlandi",
            message=f"{month_label} oyi uchun maoshlar hisoblab chiqildi. Tasdiqlashingizni kutmoqda.",
            type=NotificationType.FINANCE,
            created_at=timezone.now()
        ) for accountant in accountants
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)
        logger.info(f"{len(notifications)} ta hisobchiga bildirishnoma yuborildi.")


def _calc_meeting_penalty(user, start, end) -> Decimal:
    missed_qs = list(
        MeetingAttendance.objects
        .filter(
            user=user,
            is_attended=False,
            payroll_processed=False,
            absence_reason__isnull=True,
            is_active=True,
            meeting__is_active=True,
        )
        .exclude(meeting__organizer=user)
        .select_related("meeting")
    )

    total_penalty = Decimal("0.00")
    processed_atts = []

    for att in missed_qs:
        processed_atts.append(att.id)
        pct = att.meeting.penalty_percentage
        if pct > 0 and user.fixed_salary > 0:
            total_penalty += _round((user.fixed_salary * Decimal(str(pct))) / 100)

    if processed_atts:
        MeetingAttendance.objects.filter(id__in=processed_atts).update(payroll_processed=True)

    return total_penalty


def _calc_manager_kpi(user, start, end):
    completed_projects = list(
        Project.objects
        .filter(
            manager=user,
            status=ProjectStatus.COMPLETED,
            payroll_processed=False,
            is_active=True,
        )
    )

    kpi_bonus = Decimal("0.00")
    total_penalty = Decimal("0.00")
    processed_project_ids = []

    for project in completed_projects:
        processed_project_ids.append(project.id)
        gross = _round(project.project_price)

        if project.was_overdue:
            penalty = _round((gross * project.penalty_percentage) / 100)
            total_penalty += penalty
            kpi_bonus += (gross - penalty)
            logger.debug(
                "Manager %s | Loyiha '%s' kechikkan (was_overdue). Bonusdan %s jarima ayirildi.",
                user.username, project.title, penalty
            )
        else:
            kpi_bonus += gross

    if processed_project_ids:
        Project.objects.filter(id__in=processed_project_ids).update(payroll_processed=True)

    return kpi_bonus, total_penalty


def _calc_employee_kpi(user, start, end):
    completed_tasks = list(
        Task.objects
        .filter(
            assignee=user,
            status__in=[TaskStatus.CHECKED, TaskStatus.PRODUCTION],
            payroll_processed=False,
            is_active=True,
        )
    )

    kpi_bonus = Decimal("0.00")
    total_penalty = Decimal("0.00")
    bugs_count = 0
    processed_task_ids = []
    missed_deadlines_count = 0

    for task in completed_tasks:
        processed_task_ids.append(task.id)
        gross = _round(task.task_price)
        bugs_count += task.reopened_count

        current_task_penalty = Decimal("0.00")

        if task.reopened_count > 0:
            reopen_penalty = _round((gross * task.penalty_percentage) / 100) * task.reopened_count
            current_task_penalty += reopen_penalty

        if task.was_overdue:
            missed_deadlines_count += 1
            overdue_penalty = _round((gross * task.penalty_percentage) / 100)
            current_task_penalty += overdue_penalty
            logger.debug("Employee %s | Task '%s' kechikkan. Overdue penalty: %s", user.username, task.title,
                         overdue_penalty)

        total_penalty += current_task_penalty

        est = task.estimated_minutes or 0
        act = task.actual_minutes or 0
        velocity = Decimal(str(min(est / act, 1.0))) if est > 0 and act > 0 else Decimal("1.0")

        weighted_bonus = _round(gross * velocity) - current_task_penalty
        kpi_bonus += max(Decimal("0.00"), weighted_bonus)

    if processed_task_ids:
        Task.objects.filter(id__in=processed_task_ids).update(payroll_processed=True)

    return kpi_bonus, total_penalty, len(completed_tasks), missed_deadlines_count, bugs_count


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def calculate_monthly_salaries(self):
    now = timezone.now()
    month_start, month_end = _get_month_range(now)
    month_label = month_start.strftime("%Y-%m")

    logger.info("Oylik hisob-kitob boshlandi: %s", month_label)

    users_qs = (
        User.objects
        .filter(is_active=True)
        .only("id", "username", "roles", "fixed_salary", "balance")
        .iterator(chunk_size=500)
    )

    processed = 0
    errors = 0

    for user in users_qs:
        try:
            _process_user(user, month_start, month_end)
            processed += 1
        except Exception as exc:
            errors += 1
            logger.error(
                "Foydalanuvchi %s (%s) uchun hisoblashda xato: %s",
                user.username, user.pk, exc,
                exc_info=True,
            )

    try:
        _send_accountant_notifications(month_label)
    except Exception as e:
        logger.error(f"Hisobchilarga xabar yuborishda xatolik: {e}")

    result = f"{month_label} oyi | muvaffaqiyatli: {processed} | xato: {errors}"
    logger.info("Oylik hisob-kitob yakunlandi: %s", result)
    return result


def _process_user(user: User, month_start, month_end):
    try:
        with transaction.atomic():
            kpi_bonus = Decimal("0.00")
            total_penalty = Decimal("0.00")
            tasks_done = 0
            missed_deadlines = 0
            bugs_count = 0

            if user.has_any_role(Role.MANAGER):
                mgr_kpi, proj_penalty = _calc_manager_kpi(user, month_start, month_end)
                kpi_bonus += mgr_kpi
                total_penalty += proj_penalty

            if user.has_any_role(Role.EMPLOYEE):
                meeting_penalty = _calc_meeting_penalty(user, month_start, month_end)
                total_penalty += meeting_penalty

                emp_kpi, task_penalty, emp_tasks_done, emp_missed_deadlines, emp_bugs_count = _calc_employee_kpi(
                    user, month_start, month_end
                )
                kpi_bonus += emp_kpi
                total_penalty += task_penalty
                tasks_done += emp_tasks_done
                missed_deadlines += emp_missed_deadlines
                bugs_count += emp_bugs_count

            Payroll.objects.update_or_create(
                user=user,
                month=month_start.date(),
                defaults={
                    "fixed_salary": user.fixed_salary,
                    "kpi_bonus": kpi_bonus,
                    "penalty_amount": total_penalty,
                    "total_amount": max(Decimal("0.00"), user.fixed_salary + kpi_bonus - total_penalty),
                    "tasks_completed": tasks_done,
                    "deadline_missed": missed_deadlines,
                    "bug_count": bugs_count,
                    "is_confirmed": False
                }
            )

            logger.info(f"Muvaffaqiyatli: {user.username}")

    except Exception as exc:
        logger.error(f"Foydalanuvchi {user.username} uchun xatolik: {exc}")
        raise exc