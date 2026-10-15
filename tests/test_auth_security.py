import time

import pyotp
from cryptography.fernet import Fernet
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.auth_security import auth_throttle_keys, encrypt_secret
from accounts.models import AuthThrottle, MFADevice, SchoolMembership, User
from schools.models import School


@override_settings(
    DEBUG=True,
    MFA_REQUIRED_FOR_STAFF=True,
    MFA_REQUIRED_FOR_PRIVILEGED_ROLES=True,
    MFA_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class AuthSecurityTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Security School", slug="security-school")
        self.user = User.objects.create_user(
            username="schooladmin", email="admin@example.com", password="StrongPassword123!", is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN,
        )

    def password_login(self):
        return self.client.post(reverse("login"), {
            "username": self.user.username, "password": "StrongPassword123!",
        })

    def enroll(self):
        response = self.password_login()
        self.assertRedirects(response, reverse("mfa_enroll"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("mfa_enroll"), {"password": "StrongPassword123!"})
        secret = response.context["secret"]
        self.assertTrue(secret)
        code = pyotp.TOTP(secret).now()
        response = self.client.post(reverse("mfa_enroll"), {"code": code})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/mfa_recovery_codes.html")
        self.assertIn("_auth_user_id", self.client.session)
        return secret, response.context["codes"]

    def test_login_and_admin_password_failures_share_throttle(self):
        for _ in range(5):
            self.client.post("/admin/login/", {"username": self.user.username, "password": "bad"})
        response = self.client.post("/admin/login/", {
            "username": self.user.username, "password": "StrongPassword123!",
        })
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(response.status_code, 500)

    def test_login_throttle_covers_rotating_ips_and_success_does_not_clear_ip_history(self):
        for last_octet in range(1, 11):
            self.client.post(reverse("login"), {
                "username": self.user.username, "password": "bad",
            }, REMOTE_ADDR=f"192.0.2.{last_octet}")
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "StrongPassword123!",
        }, REMOTE_ADDR="192.0.2.99")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

        # A correct login clears identity-specific failures, never the shared IP bucket.
        ip = "198.51.100.7"
        for _ in range(5):
            self.client.post(reverse("login"), {
                "username": "different-unknown-account", "password": "bad",
            }, REMOTE_ADDR=ip)
        self.client.post(reverse("login"), {
            "username": self.user.username, "password": "StrongPassword123!",
        }, REMOTE_ADDR=ip)
        ip_key = auth_throttle_keys("login", self.user.username, type("Request", (), {"META": {"REMOTE_ADDR": ip}})())[2]
        self.assertEqual(AuthThrottle.objects.get(pk=ip_key).failures, 5)

    def test_admin_password_success_is_intercepted_before_authenticated_session_leaves(self):
        response = self.client.post("/admin/login/", {
            "username": self.user.username, "password": "StrongPassword123!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.session.get("mfa_pending_user_id"), self.user.pk)
        self.assertIn(response.url, {reverse("mfa_enroll"), reverse("mfa_challenge")})

    def test_privileged_existing_session_without_mfa_is_gated_before_portal_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("mfa_enroll"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.session.get("mfa_pending_user_id"), self.user.pk)

    def test_totp_is_required_and_replayed_step_is_rejected(self):
        secret, _ = self.enroll()
        self.client.logout()
        response = self.password_login()
        self.assertRedirects(response, reverse("mfa_challenge"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        future_step = int(time.time() // 30) + 1
        code = pyotp.TOTP(secret).at(future_step * 30)
        response = self.client.post(reverse("mfa_challenge"), {"code": code})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.client.logout()
        self.password_login()
        replay = self.client.post(reverse("mfa_challenge"), {"code": code})
        self.assertEqual(replay.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(replay, "current authenticator code")

    def test_recovery_code_is_hashed_and_one_time(self):
        _, codes = self.enroll()
        self.assertNotIn(codes[0], self.user.mfa_recovery_codes.first().code_hash)
        self.client.logout()
        self.password_login()
        response = self.client.post(reverse("mfa_challenge"), {"code": codes[0]})
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        self.password_login()
        response = self.client.post(reverse("mfa_challenge"), {"code": codes[0]})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bad_mfa_codes_are_throttled(self):
        secret, _ = self.enroll()
        self.client.logout()
        self.password_login()
        for _ in range(5):
            self.client.post(reverse("mfa_challenge"), {"code": "000000"})
        response = self.client.post(reverse("mfa_challenge"), {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_password_reset_requests_are_throttled_without_email_enumeration(self):
        for _ in range(6):
            response = self.client.post(reverse("password_reset"), {"email": "unknown@example.com"})
            self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(mail.outbox, [])

    def test_encrypted_secret_is_not_stored_as_plaintext(self):
        secret, _ = self.enroll()
        device = MFADevice.objects.get(user=self.user)
        self.assertNotIn(secret, device.encrypted_secret)

    def test_opted_in_nonprivileged_user_must_verify_mfa(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        SchoolMembership.objects.filter(user=self.user).update(role=SchoolMembership.Role.TEACHER)
        secret = pyotp.random_base32()
        MFADevice.objects.create(user=self.user, encrypted_secret=encrypt_secret(secret), enabled=True)
        response = self.password_login()
        self.assertRedirects(response, reverse("mfa_challenge"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pending_login_expires_and_password_change_invalidates_it(self):
        self.password_login()
        session = self.client.session
        session["mfa_pending_at"] = time.time() - 301
        session.save()
        expired = self.client.get(reverse("mfa_enroll"))
        self.assertRedirects(expired, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("mfa_pending_user_id", self.client.session)

        self.password_login()
        self.user.set_password("ChangedPassword456!")
        self.user.save(update_fields=["password"])
        stale = self.client.get(reverse("mfa_enroll"))
        self.assertRedirects(stale, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_encryption_key_fails_closed_without_authentication(self):
        secret, _ = self.enroll()
        self.client.logout()
        self.password_login()
        wrong_key = Fernet.generate_key().decode("ascii")
        with override_settings(MFA_ENCRYPTION_KEY=wrong_key):
            response = self.client.post(reverse("mfa_challenge"), {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_disabling_requires_current_password_and_authenticator_code(self):
        secret, _ = self.enroll()
        future_step = int(time.time() // 30) + 1
        code = pyotp.TOTP(secret).at(future_step * 30)
        response = self.client.post(reverse("mfa_disable"), {
            "password": "wrong", "code": code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(MFADevice.objects.get(user=self.user).enabled)
        response = self.client.post(reverse("mfa_disable"), {
            "password": "StrongPassword123!", "code": code,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MFADevice.objects.filter(user=self.user).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
