"""Process email outbox messages safely; simulation is the default."""

from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services.email_outbox import process_email_outbox


class Command(BaseCommand):
    help = "Process email notifications in simulation mode unless --send is explicit."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=25)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--simulate", action="store_true", default=True)
        mode.add_argument(
            "--send", action="store_true",
            help="Send actual email through Gmail API (also requires GMAIL_API_ENABLED=True).",
        )

    def handle(self, *args, **options):
        simulate = not options["send"]
        try:
            result = process_email_outbox(
                batch_size=options["batch_size"], simulate=simulate,
            )
        except (RuntimeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        mode = "simulation" if simulate else "Gmail API"
        self.stdout.write(self.style.SUCCESS(
            f"Email outbox {mode}: processed={result['processed']}, "
            f"simulated={result['simulated']}, accepted_by_gmail={result['accepted_by_gmail']}, "
            f"failed={result['failed']}, retries={result['retry_scheduled']}, "
            f"send_outcome_unknown={result['send_outcome_unknown']}, "
            f"stale_needing_review={result['stale_claims_needing_review']}."
        ))
