from django.utils import timezone

from .auth_utils import request_can_edit
from .models import Installment


def access_context(request):
    overdue_member_ids = list(
        Installment.objects.filter(due_date__lt=timezone.localdate())
        .exclude(status=Installment.Status.PAID)
        .values_list("loan__member_id", flat=True)
        .distinct()
    )
    return {
        "can_edit": request_can_edit(request),
        "overdue_member_ids": overdue_member_ids,
    }
