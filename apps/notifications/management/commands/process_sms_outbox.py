"""Process queued SMS messages in safe simulation mode only."""

from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services.sms_outbox import process_sms_outbox


class Command(BaseCommand):
    help = "Process queued SMS messages without transmitting real SMS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--simulate",
            action="store_true",
            help="Required safety flag. Records simulated outcomes only.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Maximum number of messages to process (1-500).",
        )

    def handle(self, *args, **options):
        if not options["simulate"]:
            raise CommandError(
                "Simulation must be explicitly enabled with --simulate. "
                "Real SMS delivery is not implemented."
            )

        try:
            result = process_sms_outbox(
                batch_size=options["batch_size"],
                simulate=True,
            )
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "SMS outbox simulation completed: "
                f"processed={result['processed']}, "
                f"simulated={result['simulated']}, "
                f"failed={result['failed']}, "
                f"recovered={result['recovered']}, "
                f"exhausted={result['exhausted']}, "
                "real_sms_sent=False"
            )
        )
