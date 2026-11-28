from django.core.management.base import BaseCommand

from apps.identity_cards.services.office_appointment import (
    expire_due_office_appointments,
)


class Command(BaseCommand):
    help = "End expired Diocesan office appointments and restore personal identities."

    def handle(self, *args, **options):
        ended_count = expire_due_office_appointments()
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {ended_count} Diocesan office appointment(s)."
            )
        )
