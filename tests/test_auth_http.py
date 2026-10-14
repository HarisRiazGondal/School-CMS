from urllib.parse import urlparse

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import SchoolMembership, User
from schools.models import School


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthHTTPTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north-school")
        self.other_school = School.objects.create(name="Old School", slug="old-school", is_active=False)
        self.user = User.objects.create_user(
            username="teacher", email="teacher@example.com", password="StrongPassword123!"
        )
        SchoolMembership.objects.create(user=self.user, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.user, school=self.other_school, role=SchoolMembership.Role.STUDENT)

    def test_login_requires_csrf_and_accepts_username(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("login"), {"username": "teacher", "password": "StrongPassword123!"})
        self.assertEqual(response.status_code, 403)
        response = client.get(reverse("login"))
        token = client.cookies["csrftoken"].value
        response = client.post(reverse("login"), {
            "username": "teacher", "password": "StrongPassword123!", "csrfmiddlewaretoken": token,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_login_rejects_deactivated_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(reverse("login"), {
            "username": "teacher", "password": "StrongPassword123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "did not match an active account")

    def test_dashboard_only_renders_active_school_memberships(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North School")
        self.assertNotContains(response, "Old School")

    def test_deactivated_user_session_is_ended(self):
        self.client.force_login(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_is_post_only_and_csrf_protected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        response = client.post(reverse("logout"))
        self.assertEqual(response.status_code, 403)
        response = client.get(reverse("home"))
        token = client.cookies["csrftoken"].value
        response = client.post(reverse("logout"), {"csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("logged_out"))
        self.assertNotIn("_auth_user_id", client.session)

    def test_password_reset_sends_usable_link_and_changes_password(self):
        response = self.client.post(reverse("password_reset"), {"email": "teacher@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        reset_url = mail.outbox[0].body.splitlines()[5]
        path = urlparse(reset_url).path
        response = self.client.get(path, follow=True)
        self.assertEqual(response.status_code, 200)
        # Django's confirmation view replaces the one-time token with a session-bound token.
        response = self.client.post(response.request["PATH_INFO"], {
            "new_password1": "ChangedPassword456!", "new_password2": "ChangedPassword456!",
        })
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ChangedPassword456!"))

    def test_password_reset_is_enumeration_safe_for_unknown_email(self):
        response = self.client.post(reverse("password_reset"), {"email": "unknown@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_does_not_send_for_deactivated_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(reverse("password_reset"), {"email": "teacher@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
