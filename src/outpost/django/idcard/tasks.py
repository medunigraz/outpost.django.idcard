import logging

from celery import shared_task

from .models import EmployeeCard

logger = logging.getLogger(__name__)


class CardTasks:
    @shared_task(bind=True, ignore_result=True, name=f"{__name__}.Card:google_push")
    def google_push(task, pk):
        card = EmployeeCard.objects.select_related("person").get(pk=pk)
        logger.info(f"Pushing Google Wallet object for {card}")
        card.google_push()

    @shared_task(bind=True, ignore_result=True, name=f"{__name__}.Card:synchronize")
    def synchronize(task):
        logger.info("Revoking and pushing cards against current CAMPUSonline data")
        # No select_related: its inner join would skip cards whose Person is gone,
        # and those are exactly the ones to revoke.
        pushed = 0
        for card in EmployeeCard.objects.all():
            try:
                pushed += card.synchronize()
            except Exception:
                logger.exception(f"Synchronizing {card} failed")
        logger.info(f"Pushed {pushed} changed cards")
