"""
Seed demo users and test evaluation documents.
"""

import os
from PIL import Image, ImageDraw, ImageFont
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from django.core.files import File
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from documents.models import Document, RecognitionResult
from accounts.models import UserProfile


class Command(BaseCommand):
    help = 'Seeds initial superuser, student demo account, and evaluation sample documents.'

    def handle(self, *args, **options):
        # 1. Create superuser
        admin_user, created_admin = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@multilingualhtr.local',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created_admin:
            admin_user.set_password('AdminPass123!')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created superuser 'admin' (password: AdminPass123!)."))
        else:
            self.stdout.write("Superuser 'admin' already exists.")

        # 2. Create demo student user
        demo_user, created_demo = User.objects.get_or_create(
            username='student',
            defaults={
                'email': 'student@university.edu',
                'first_name': 'Ravi',
                'last_name': 'Kumar',
            }
        )
        if created_demo:
            demo_user.set_password('StudentPass123!')
            demo_user.save()
            profile, _ = UserProfile.objects.get_or_create(user=demo_user)
            profile.organization = 'Department of Computer Science & Engineering'
            profile.preferred_language = 'te'
            profile.save()
            self.stdout.write(self.style.SUCCESS("Created demo user 'student' (password: StudentPass123!)."))
        else:
            self.stdout.write("Demo user 'student' already exists.")

        # 3. Create Sample Documents
        samples_dir = os.path.join(settings.MEDIA_ROOT, 'samples')
        os.makedirs(samples_dir, exist_ok=True)

        # Sample A: Printed English
        en_img_path = os.path.join(samples_dir, 'sample_printed_english.png')
        img_en = Image.new('RGB', (800, 300), color=(255, 255, 255))
        d_en = ImageDraw.Draw(img_en)
        d_en.text((40, 40), "Multilingual Handwritten and Printed Recognition System", fill=(0, 0, 0))
        d_en.text((40, 90), "Natural language processing and optical character recognition.", fill=(30, 30, 30))
        d_en.text((40, 140), "Testing high-resolution printed text lines for accurate extraction.", fill=(30, 30, 30))
        d_en.text((40, 190), "Academic Project Demonstration 2026.", fill=(50, 50, 50))
        img_en.save(en_img_path)

        # Sample B: Cursive / Handwritten English
        hw_img_path = os.path.join(samples_dir, 'sample_handwritten_english.png')
        img_hw = Image.new('RGB', (800, 300), color=(250, 248, 240))
        d_hw = ImageDraw.Draw(img_hw)
        # Draw cursive-like lines
        d_hw.text((40, 50), "Dear student, please submit the project report by Friday.", fill=(15, 23, 42))
        d_hw.text((40, 110), "Ensure all references and accuracy metrics are included.", fill=(15, 23, 42))
        d_hw.text((40, 170), "Best regards, Faculty Advisory Board.", fill=(15, 23, 42))
        # Add subtle simulated rule lines
        for y in [95, 155, 215]:
            d_hw.line([(30, y), (770, y)], fill=(220, 225, 235), width=1)
        img_hw.save(hw_img_path)

        # Sample C: Multi-page PDF
        pdf_path = os.path.join(samples_dir, 'sample_multipage_notes.pdf')
        pdf_doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph("<b>Page 1: Project Abstract</b>", styles['Heading1']),
            Spacer(1, 12),
            Paragraph("This document demonstrates multi-page OCR extraction. The pipeline renders each page independently and tracks page-level boundaries.", styles['Normal']),
            Spacer(1, 100),
            Paragraph("<b>Page 2: Multilingual Support</b>", styles['Heading1']),
            Spacer(1, 12),
            Paragraph("Testing second page text. Indian scripts such as Telugu and Hindi are supported alongside English.", styles['Normal']),
        ]
        pdf_doc.build(elements)

        # Seed in database for demo_user if no docs exist
        if not Document.objects.filter(user=demo_user).exists():
            with open(en_img_path, 'rb') as f:
                doc_en = Document.objects.create(
                    user=demo_user,
                    title="Printed English Abstract",
                    original_filename="sample_printed_english.png",
                    selected_language='en',
                    document_type='printed',
                    file_size=os.path.getsize(en_img_path),
                    status='completed',
                    page_count=1
                )
                doc_en.original_file.save("sample_printed_english.png", File(f), save=True)

                RecognitionResult.objects.create(
                    document=doc_en,
                    page_number=1,
                    original_recognized_text=(
                        "Multilingual Handwritten and Printed Recognition System\n"
                        "Natural language processing and optical character recognition.\n"
                        "Testing high-resolution printed text lines for accurate extraction.\n"
                        "Academic Project Demonstration 2026."
                    ),
                    edited_text=(
                        "Multilingual Handwritten and Printed Recognition System\n"
                        "Natural language processing and optical character recognition.\n"
                        "Testing high-resolution printed text lines for accurate extraction.\n"
                        "Academic Project Demonstration 2026."
                    ),
                    confidence=96.4,
                    processing_duration=0.38,
                    provider_name='easyocr'
                )

            with open(hw_img_path, 'rb') as f:
                doc_hw = Document.objects.create(
                    user=demo_user,
                    title="Faculty Handwriting Note",
                    original_filename="sample_handwritten_english.png",
                    selected_language='en',
                    document_type='handwritten',
                    file_size=os.path.getsize(hw_img_path),
                    status='pending',
                    page_count=1
                )
                doc_hw.original_file.save("sample_handwritten_english.png", File(f), save=True)

            with open(pdf_path, 'rb') as f:
                doc_pdf = Document.objects.create(
                    user=demo_user,
                    title="Multi-Page Lecture Notes",
                    original_filename="sample_multipage_notes.pdf",
                    selected_language='en',
                    document_type='printed',
                    file_size=os.path.getsize(pdf_path),
                    status='pending',
                    page_count=2
                )
                doc_pdf.original_file.save("sample_multipage_notes.pdf", File(f), save=True)

            self.stdout.write(self.style.SUCCESS("Created initial demo documents for 'student'."))

        self.stdout.write(self.style.SUCCESS("Seeding completed successfully!"))
