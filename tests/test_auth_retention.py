from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.auth_retention import database_now, prune_stale_throttles
from accounts.models import AuthThrottle


class AuthThrottleRetentionTests(TestCase):
    def create_bucket(self, key, *, window_started, blocked_until=None):
        return AuthThrottle.objects.create(
            key=key, window_started=window_started, blocked_until=blocked_until,
        )

    def test_dry_run_and_apply_preserve_currently_blocked_buckets(self):
        now = database_now()
        old = now - timedelta(days=40)
        stale = self.create_bucket("stale", window_started=old)
        expired_block = self.create_bucket(
            "expired-block", window_started=old, blocked_until=now - timedelta(seconds=1),
        )
        active_block = self.create_bucket(
            "active-block", window_started=old, blocked_until=now + timedelta(minutes=2),
        )
        recent = self.create_bucket("recent", window_started=now - timedelta(days=2))

        preview = prune_stale_throttles(older_than_days=30, batch_size=10)
        self.assertEqual(preview["eligible"], 2)
        self.assertEqual(preview["deleted"], 0)
        self.assertFalse(preview["has_more"])
        self.assertTrue(AuthThrottle.objects.filter(pk=stale.pk).exists())
        self.assertTrue(AuthThrottle.objects.filter(pk=expired_block.pk).exists())

        applied = prune_stale_throttles(older_than_days=30, batch_size=10, apply=True)
        self.assertEqual(applied["deleted"], 2)
        self.assertFalse(AuthThrottle.objects.filter(pk__in=[stale.pk, expired_block.pk]).exists())
        self.assertTrue(AuthThrottle.objects.filter(pk=active_block.pk).exists())
        self.assertTrue(AuthThrottle.objects.filter(pk=recent.pk).exists())

    def test_pruning_is_bounded_and_reports_more_rows_without_identifiers(self):
        old = database_now() - timedelta(days=45)
        for n in range(4):
            self.create_bucket(f"private-key-{n}", window_started=old)

        output = StringIO()
        call_command("prune_auth_throttles", "--batch-size=2", stdout=output)
        self.assertIn("eligible this batch=2", output.getvalue())
        self.assertIn("deleted=0", output.getvalue())
        self.assertIn("More eligible rows remain", output.getvalue())
        for n in range(4):
            self.assertTrue(AuthThrottle.objects.filter(pk=f"private-key-{n}").exists())

        result = prune_stale_throttles(batch_size=2, apply=True)
        self.assertEqual(result["eligible"], 2)
        self.assertEqual(result["deleted"], 2)
        self.assertTrue(result["has_more"])
        self.assertNotIn("private-key", output.getvalue())

    def test_invalid_limits_fail_without_running_pruning(self):
        for args in (("--older-than-days=0",), ("--batch-size=10001",)):
            with self.subTest(args=args), self.assertRaises(CommandError):
                call_command("prune_auth_throttles", *args, stdout=StringIO())

    def test_database_clock_is_timezone_aware(self):
        self.assertIsNotNone(timezone.now() - database_now())
