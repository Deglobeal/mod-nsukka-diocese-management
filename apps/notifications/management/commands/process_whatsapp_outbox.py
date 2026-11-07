"""Process queued WhatsApp messages in safe simulation mode only."""

from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services.whatsapp_outbox import (
    process_whatsapp_outbox,
)


class Command(BaseCommand):
    help = (
        "Process queued WhatsApp messages without transmitting "
        "real WhatsApp messages."
    )

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
                "Real WhatsApp delivery is not implemented."
            )

        try:
            result = process_whatsapp_outbox(
                batch_size=options["batch_size"],
                simulate=True,
            )
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "WhatsApp outbox simulation completed: "
                f"processed={result['processed']}, "
                f"simulated={result['simulated']}, "
                f"failed={result['failed']}, "
                f"recovered={result['recovered']}, "
                f"exhausted={result['exhausted']}, "
                "real_whatsapp_sent=False"
            )
        )
