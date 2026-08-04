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
        ) for accountant in accountants
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)
        logger.info("%d ta hisobchiga bildirishnoma yuborildi.", len(notifications))


def _calc_meeting_penalty(user):
    missed_qs = list(
        MeetingAttendance.objects
        .filter(
            user=user,
            is_attended=False,
            payroll_processed=False,
            is_excused=False,
            is_active=True,
            meeting__is_active=True,
        )
        .exclude(meeting__organizer=user)
        .select_related("meeting")
    )

    total_penalty = Decimal("0.00")
    reasons = []
    processed_atts = []

    for att in missed_qs:
        processed_atts.append(att.id)
        pct = att.meeting.penalty_percentage
        if pct > 0 and user.fixed_salary > 0:
            penalty = _round((user.fixed_salary * Decimal(str(pct))) / 100)
            total_penalty += penalty
            reasons.append(f'"{att.meeting.title}" meetga sababsiz kirmaganingiz uchun {pct}% ({penalty} so\'m) minus bo\'lgan')

    if processed_atts:
        MeetingAttendance.objects.filter(id__in=processed_atts).update(payroll_processed=True)

    return total_penalty, reasons, len(missed_qs)


def _calc_manager_kpi(user):
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
    reasons = []
    processed_project_ids = []

    for project in completed_projects:
        processed_project_ids.append(project.id)
        gross = _round(project.project_price)
        penalty_base = gross if gross > 0 else user.fixed_salary

        if project.was_overdue and penalty_base > 0:
            penalty = _round((penalty_base * project.penalty_percentage) / 100)
            total_penalty += penalty
            reasons.append(f'"{project.title}" loyihasi uchun muddat qo\'shilgan {project.penalty_percentage}% ({penalty} so\'m) minus bo\'lgan')
            logger.debug("Manager %s | Loyiha '%s' kechikkan. Jarima: %s", user.username, project.title, penalty)

        kpi_bonus += gross

    if processed_project_ids:
        Project.objects.filter(id__in=processed_project_ids).update(payroll_processed=True)

    return kpi_bonus, total_penalty, reasons


def _calc_employee_kpi(user):
    completed_tasks = list(
        Task.objects
        .filter(
            assignee=user,
            status=TaskStatus.CHECKED,
            payroll_processed=False,
            is_active=True,
        )
    )

    kpi_bonus = Decimal("0.00")
    total_penalty = Decimal("0.00")
    bugs_count = 0
    reasons = []
    processed_task_ids = []
    missed_deadlines_count = 0

    for task in completed_tasks:
        processed_task_ids.append(task.id)
        gross = _round(task.task_price)
        bugs_count += task.reopened_count

        current_task_penalty = Decimal("0.00")
        penalty_base = gross if gross > 0 else user.fixed_salary

        if penalty_base > 0:
            if task.reopened_count > 0:
                reopen_penalty = _round((penalty_base * task.penalty_percentage) / 100) * task.reopened_count
                current_task_penalty += reopen_penalty
                total_reopen_pct = task.penalty_percentage * task.reopened_count
                reasons.append(f'"{task.title}" task {task.reopened_count} marta qayta ochilgani uchun {total_reopen_pct}% ({reopen_penalty} so\'m) minus bo\'lgan')

            if task.was_overdue:
                missed_deadlines_count += 1
                overdue_penalty = _round((penalty_base * task.penalty_percentage) / 100)
                current_task_penalty += overdue_penalty
                reasons.append(f'"{task.title}" task uchun muddat qo\'shilgan {task.penalty_percentage}% ({overdue_penalty} so\'m) minus bo\'lgan')
                logger.debug("Employee %s | Task '%s' kechikkan. Jarima: %s", user.username, task.title,
                             overdue_penalty)

        total_penalty += current_task_penalty

        est = task.estimated_minutes or 0
        act = task.actual_minutes or 0
        velocity = Decimal(str(min(est / act, 1.0))) if est > 0 and act > 0 else Decimal("1.0")
        kpi_bonus += _round(gross * velocity)

    if processed_task_ids:
        Task.objects.filter(id__in=processed_task_ids).update(payroll_processed=True)

    return kpi_bonus, total_penalty, len(completed_tasks), missed_deadlines_count, bugs_count, reasons


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

    processed = errors = 0

    for user in users_qs:
        try:
            _process_user(user, month_start, month_end)
            processed += 1
        except Exception as exc:
            errors += 1
            logger.error("Foydalanuvchi %s (%s) uchun hisoblashda xato: %s", user.username, user.pk, exc, exc_info=True)

    try:
        _send_accountant_notifications(month_label)
    except Exception as e:
        logger.error("Hisobchilarga xabar yuborishda xatolik: %s", e)

    result = f"{month_label} oyi | muvaffaqiyatli: {processed} | xato: {errors}"
    logger.info("Oylik hisob-kitob yakunlandi: %s", result)
    return result


def _process_user(user: User, month_start, month_end):
    with transaction.atomic():
        kpi_bonus = Decimal("0.00")
        total_penalty = Decimal("0.00")
        tasks_done = missed_deadlines = bugs_count = missed_meetings_count = 0
        reasons = []

        if user.has_any_role(Role.MANAGER):
            mgr_kpi, proj_penalty, mgr_reasons = _calc_manager_kpi(user)
            kpi_bonus += mgr_kpi
            total_penalty += proj_penalty
            reasons.extend(mgr_reasons)

        if user.has_any_role(Role.EMPLOYEE):
            meet_penalty, meet_reasons, missed_meetings_count = _calc_meeting_penalty(user)
            total_penalty += meet_penalty
            reasons.extend(meet_reasons)

            emp_kpi, task_penalty, tasks_done, missed_deadlines, bugs_count, emp_reasons = _calc_employee_kpi(user)
            kpi_bonus += emp_kpi
            total_penalty += task_penalty
            reasons.extend(emp_reasons)

        reason_text = "\n".join(reasons) if reasons else None

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
                "missed_meetings_count": missed_meetings_count,
                "reason": reason_text,
                "is_confirmed": False,
            }
        )
