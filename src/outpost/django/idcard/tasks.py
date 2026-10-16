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
        logger.info("Pushing current CAMPUSonline data to all Google Wallet objects")
        for card in EmployeeCard.objects.exclude(google_pass_id=None).select_related(
            "person"
        ):
            card.google_push()
