from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.finance.models import ExpenseRequest, Status, ExpenseType, Ledger, TransactionType

User = get_user_model()

@receiver(pre_save, sender=ExpenseRequest)
def expense_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
    else:
        try:
            old_instance = ExpenseRequest.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except ExpenseRequest.DoesNotExist:
            instance._old_status = None

    if getattr(instance, '_old_status', None) != Status.CONFIRMED and instance.status == Status.CONFIRMED:
        if not instance.confirmed_at:
            instance.confirmed_at = timezone.now()


@receiver(post_save, sender=ExpenseRequest)
def expense_post_save(sender, instance, created, **kwargs):
    if not created:
        _old_status = getattr(instance, '_old_status', None)
        
        if _old_status != Status.CONFIRMED and instance.status == Status.CONFIRMED:
            if instance.type == ExpenseType.WITHDRAWAL:

                user = User.objects.select_for_update().get(pk=instance.user_id)
                if user.balance < instance.amount:
                    raise ValidationError("Balansda yetarli mablag' qolmagan!")
                
                user.balance -= instance.amount
                user.save(update_fields=['balance'])
                
            reason_text = instance.reason if instance.reason else "Ko'rsatilmagan"
            Ledger.objects.get_or_create(
                expense=instance,
                defaults={
                    'user': instance.user,
                    'amount': instance.amount,
                    'transaction_type': TransactionType.DEBIT,
                    'description': f"{instance.get_type_display()} tasdiqlandi. Sabab: {reason_text}"
                }
            )
