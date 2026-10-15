import io
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from learning.models import Assignment, AttendanceRecord, Submission
from students.models import Student, Enrollment
from accounts.models import User

@override_settings(DEBUG=True)
class PilotBrowserFlowTests(TestCase):
    def setUp(self):
        self.password = 'Synthetic-Test-Only-91'
        call_command('seed_demo', password=self.password, stdout=io.StringIO())

    def test_demo_is_idempotent_and_each_role_dashboard_renders(self):
        counts = (User.objects.count(), Student.objects.count(), Enrollment.objects.count(), Assignment.objects.count())
        call_command('seed_demo', password=self.password, stdout=io.StringIO())
        self.assertEqual(counts, (User.objects.count(), Student.objects.count(), Enrollment.objects.count(), Assignment.objects.count()))
        for username in ['demo-admin', 'demo-registrar', 'demo-teacher', 'demo-student']:
            with self.subTest(role=username):
                client = Client(enforce_csrf_checks=True)
                login = client.get(reverse('login'))
                self.assertEqual(login.status_code, 200)
                token = client.cookies['csrftoken'].value
                response = client.post(reverse('login'), {'username':username, 'password':self.password, 'csrfmiddlewaretoken':token}, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Welcome')
                if username != 'demo-registrar':
                    self.assertEqual(client.get(reverse('learning:home')).status_code, 200)
                if username in ['demo-admin','demo-registrar']:
                    self.assertEqual(client.get(reverse('students:list', kwargs={'school_slug':'demo-school'})).status_code, 200)

    def test_teacher_attendance_and_student_submission_http_flow(self):
        enrollment = Enrollment.objects.get(student__user__username='demo-student')
        assignment = Assignment.objects.get(title='Fractions practice')
        self.client.login(username='demo-teacher', password=self.password)
        url = reverse('learning:attendance-entry', args=[enrollment.section_id])
        self.assertEqual(self.client.get(url).status_code, 200)
        attendance_date = timezone.localdate()
        response = self.client.post(url, {'date':attendance_date.isoformat(), f'status_{enrollment.pk}':'present'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AttendanceRecord.objects.get(enrollment=enrollment, session__date=attendance_date).status,'present')
        self.client.logout()
        self.client.login(username='demo-student',password=self.password)
        response = self.client.post(reverse('learning:assignment-submit',args=[assignment.pk]), {'response':'Synthetic fractions answer'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Submission.objects.get(enrollment=enrollment).response,'Synthetic fractions answer')

    def test_browser_promotion_preview_confirmation_and_history(self):
        student = Student.objects.get(user__username='demo-student')
        source = Enrollment.objects.get(student=student)
        from academics.models import Section
        from schools.models import AcademicYear
        target = AcademicYear.objects.filter(school=student.school).order_by('-starts_on').first()
        section = Section.objects.get(academic_year=target)
        kwargs = {'school_slug':'demo-school', 'student_code':student.student_code, 'year_name':source.academic_year.name}
        payload = {'outcome':'promoted','target_year':target.pk,'target_section':section.pk,'roll_number':'08'}
        self.client.login(username='demo-admin',password=self.password)
        preview = self.client.post(reverse('students:promotion-preview',kwargs=kwargs),payload)
        self.assertEqual(preview.status_code,200)
        self.assertContains(preview,'Confirm outcome')
        self.assertEqual(Enrollment.objects.filter(student=student).count(),1)
        self.client.logout()
        self.client.login(username='demo-registrar',password=self.password)
        self.assertEqual(self.client.post(reverse('students:promotion-confirm',kwargs=kwargs),payload).status_code,403)
        self.client.logout()
        self.client.login(username='demo-admin',password=self.password)
        result = self.client.post(reverse('students:promotion-confirm',kwargs=kwargs),payload)
        self.assertEqual(result.status_code,302)
        source.refresh_from_db()
        self.assertEqual(source.status,'promoted')
        self.assertEqual(Enrollment.objects.filter(student=student).count(),2)
        self.assertEqual(Enrollment.objects.get(student=student,academic_year=target).roll_number,'08')
        call_command('seed_demo', password=self.password, stdout=io.StringIO())
        source.refresh_from_db()
        self.assertEqual(source.status,'promoted')
