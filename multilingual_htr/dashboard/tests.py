from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from documents.models import Document, RecognitionResult

class DashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='dashuser', password='Password123!')
        self.client.login(username='dashuser', password='Password123!')

    def test_dashboard_renders_stats(self):
        # Create documents with different statuses
        d1 = Document.objects.create(
            user=self.user,
            title="Doc 1",
            original_filename="doc1.png",
            selected_language='te',
            document_type='printed',
            status='completed'
        )
        RecognitionResult.objects.create(
            document=d1,
            page_number=1,
            original_recognized_text="నమస్కారం",
            confidence=92.0,
            provider_name='easyocr'
        )

        d2 = Document.objects.create(
            user=self.user,
            title="Doc 2",
            original_filename="doc2.png",
            selected_language='hi',
            document_type='handwritten',
            status='pending'
        )

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doc 1")
        self.assertContains(response, "Doc 2")
        self.assertEqual(response.context['total_documents'], 2)
        self.assertEqual(response.context['completed_count'], 1)
        self.assertEqual(response.context['pending_count'], 1)
        self.assertEqual(response.context['avg_confidence'], 92.0)
