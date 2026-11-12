from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import UserProfile


class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('accounts:register')
        self.login_url = reverse('accounts:login')
        self.logout_url = reverse('accounts:logout')
        self.profile_url = reverse('accounts:profile')
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='Password123!'
        )

    def test_user_registration(self):
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
            'preferred_language': 'te'
        })
        self.assertEqual(response.status_code, 302)
        new_user = User.objects.get(username='newuser')
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.profile.preferred_language, 'te')

    def test_user_registration_mismatched_password(self):
        response = self.client.post(self.register_url, {
            'username': 'mismatchuser',
            'email': 'mismatch@example.com',
            'password': 'StrongPassword123!',
            'confirm_password': 'DifferentPassword123!',
            'preferred_language': 'en'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='mismatchuser').exists())

    def test_user_login_and_logout(self):
        # Login
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'Password123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue('_auth_user_id' in self.client.session)

        # Logout
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_profile_access_restriction(self):
        # Unauthenticated redirect to login
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.login_url, response.url)

        # Authenticated access
        self.client.login(username='testuser', password='Password123!')
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'testuser')

    def test_profile_update(self):
        self.client.login(username='testuser', password='Password123!')
        response = self.client.post(self.profile_url, {
            'first_name': 'Test',
            'last_name': 'Developer',
            'email': 'updated@example.com',
            'organization': 'Engineering Institute',
            'preferred_language': 'hi',
            'preferred_engine': 'easyocr',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Test')
        self.assertEqual(self.user.profile.organization, 'Engineering Institute')
        self.assertEqual(self.user.profile.preferred_language, 'hi')
