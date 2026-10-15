from django.core.management.base import BaseCommand, CommandError

from accounts.auth_retention import prune_stale_throttles


class Command(BaseCommand):
    help = "Inspect or prune a bounded batch of expired authentication throttle buckets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days", type=int, default=30,
            help="Minimum age of the throttle window to consider (1–3650 days; default: 30).",
        )
        parser.add_argument(
            "--batch-size", type=int, default=1000,
            help="Maximum rows to inspect/delete in one run (1–10000; default: 1000).",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Delete eligible rows. Without this flag the command only reports a dry run.",
        )

    def handle(self, *args, **options):
        older_than_days = options["older_than_days"]
        batch_size = options["batch_size"]
        if not 1 <= older_than_days <= 3650:
            raise CommandError("--older-than-days must be between 1 and 3650.")
        if not 1 <= batch_size <= 10000:
            raise CommandError("--batch-size must be between 1 and 10000.")

        result = prune_stale_throttles(
            older_than_days=older_than_days,
            batch_size=batch_size,
            apply=options["apply"],
        )
        mode = "applied" if options["apply"] else "dry-run"
        continuation = " More eligible rows remain; run again to continue." if result["has_more"] else ""
        self.stdout.write(
            f"Auth throttle retention {mode}: eligible this batch={result['eligible']}; "
            f"deleted={result['deleted']}; cutoff={result['cutoff'].isoformat()}; "
            f"database_time={result['database_now'].isoformat()}.{continuation}"
        )
