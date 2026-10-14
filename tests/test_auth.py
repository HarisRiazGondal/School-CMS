from django.test import TestCase

from accounts.models import SchoolMembership, User, has_school_role
from schools.models import School

class SchoolMembershipTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", slug="test-school")
        self.other_school = School.objects.create(name="Other School", slug="other-school")
        self.user = User.objects.create_user(
            username="teacher1", email="teacher1@example.com", password="safe-test-password"
        )

    def test_active_membership_grants_only_matching_role_and_school(self):
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=SchoolMembership.Role.TEACHER,
        )
        self.assertTrue(has_school_role(self.user, self.school, SchoolMembership.Role.TEACHER))
        self.assertFalse(has_school_role(self.user, self.school, SchoolMembership.Role.ACCOUNTANT))
        self.assertFalse(has_school_role(self.user, self.other_school, SchoolMembership.Role.TEACHER))

    def test_inactive_membership_is_denied(self):
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=SchoolMembership.Role.TEACHER,
            is_active=False,
        )
        self.assertFalse(has_school_role(self.user, self.school, SchoolMembership.Role.TEACHER))

    def test_anonymous_user_is_denied(self):
        self.user.is_authenticated = False
        self.assertFalse(has_school_role(self.user, self.school, SchoolMembership.Role.TEACHER))
