import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.forms.models import model_to_dict
from .models import AuditLog, ActionType
from .middleware import get_current_request

AUDITED_MODELS = [
    'Project', 'Task', 'TaskAttachment',
    'ExpenseCategory', 'ExpenseRequest', 'Payroll',
    'Meeting', 'MeetingAttendance'
]


class AuditJSONEncoder(DjangoJSONEncoder):
    def default(self, o):
        if hasattr(o, 'pk'):
            return o.pk
        return super().default(o)


def serialize_data(data):
    return json.loads(json.dumps(data, cls=AuditJSONEncoder))


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
        return ip

    real_ip = request.META.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip

    return request.META.get('REMOTE_ADDR')


@receiver(pre_save)
def audit_pre_save(sender, instance, **kwargs):
    if sender.__name__ not in AUDITED_MODELS:
        return

    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_values = model_to_dict(old_instance)
        except sender.DoesNotExist:
            instance._old_values = {}
    else:
        instance._old_values = {}


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    if sender.__name__ not in AUDITED_MODELS:
        return

    request = get_current_request()

    def create_log():
        instance.refresh_from_db()

        if created:
            action = ActionType.CREATE
        else:
            new_status = getattr(instance, 'status', None)
            old_values_dict = getattr(instance, '_old_values', {})
            old_status = old_values_dict.get('status')

            if new_status == 'confirmed' and old_status != 'confirmed':
                action = ActionType.CONFIRM
            else:
                action = ActionType.UPDATE

        new_values = serialize_data(model_to_dict(instance))
        old_values = serialize_data(getattr(instance, '_old_values', {}))

        if not created:
            changes = {k: v for k, v in new_values.items() if v != old_values.get(k)}
            if not changes:
                return
            old_values = {k: old_values.get(k) for k in changes.keys()}
            new_values = changes

        AuditLog.objects.create(
            user=request.user if request and request.user.is_authenticated else None,
            action=action,
            ip_address=get_client_ip(request) if request else None,
            table_name=sender._meta.db_table,
            record_id=instance.pk,
            old_values=old_values,
            new_values=new_values
        )

    transaction.on_commit(create_log)


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    if sender.__name__ not in AUDITED_MODELS:
        return

    request = get_current_request()

    AuditLog.objects.create(
        user=request.user if request and request.user.is_authenticated else None,
        action=ActionType.DELETE,
        ip_address=get_client_ip(request) if request else None,
        table_name=sender._meta.db_table,
        record_id=instance.pk,
        old_values=serialize_data(model_to_dict(instance)),
        new_values=None
    )
