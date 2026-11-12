import io
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from PIL import Image
import numpy as np

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User

from documents.models import Document, RecognitionResult, RecognitionJob, TranslationResult
from documents.forms import DocumentUploadForm, RecognitionConfigForm
from documents.services.language_registry import LanguageRegistry
from documents.services.preprocessing import PreprocessingPipeline
from documents.services.ocr_service import OCRService
from documents.services.export_service import ExportService
from documents.services.trocr_engine import TrOCREngine
from documents.services.easyocr_engine import EasyOCREngine
from documents.services.google_vision_engine import GoogleVisionEngine
from documents.services.translation_service import TranslationService
from documents.services.pdf_service import PDFService
from documents.services.medical_extractor import MedicalPrescriptionExtractor
from documents.services.bank_extractor import BankRecordExtractor
from documents.services.technical_postprocessor import TechnicalPostProcessor
from documents.management.commands.evaluate_accuracy import calculate_cer, calculate_wer


class DocumentTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_media = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(username='usera', password='Password123!')
        self.user_b = User.objects.create_user(username='userb', password='Password123!')

    def _create_dummy_image(self, filename='test.png', size=(200, 100), color=(255, 255, 255)):
        img = Image.new('RGB', size, color=color)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile(filename, buf.read(), content_type='image/png')

    def _create_dummy_jpeg(self, filename='test.jpg', size=(200, 100), color=(255, 255, 255)):
        img = Image.new('RGB', size, color=color)
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        return SimpleUploadedFile(filename, buf.read(), content_type='image/jpeg')

    def test_language_capability_registry(self):
        # English is supported by all 3 engines
        for eng in ['easyocr', 'trocr', 'google_vision']:
            is_compat, _ = LanguageRegistry.is_engine_compatible(eng, 'en', 'printed')
            self.assertTrue(is_compat)

        # Telugu & Hindi are supported by EasyOCR and Google Vision, NOT TrOCR
        is_compat_te, _ = LanguageRegistry.is_engine_compatible('easyocr', 'te', 'printed')
        self.assertTrue(is_compat_te)

        is_compat_hi, _ = LanguageRegistry.is_engine_compatible('easyocr', 'hi', 'printed')
        self.assertTrue(is_compat_hi)

        is_compat_trocr_te, reason_te = LanguageRegistry.is_engine_compatible('trocr', 'te', 'printed')
        self.assertFalse(is_compat_trocr_te)
        self.assertIn("does not support Telugu", reason_te)

        is_compat_trocr_hi, reason_hi = LanguageRegistry.is_engine_compatible('trocr', 'hi', 'printed')
        self.assertFalse(is_compat_trocr_hi)
        self.assertIn("does not support Hindi", reason_hi)

    def test_opencv_preprocessing(self):
        # Create a test numpy image with simulated tilted line
        img_arr = np.ones((150, 300, 3), dtype=np.uint8) * 255
        options = {
            'apply_deskew': True,
            'apply_clahe': True,
            'apply_denoising': True,
            'apply_threshold': True,
        }
        processed, _ = PreprocessingPipeline.apply(img_arr, options=options)
        self.assertIsNotNone(processed)
        self.assertEqual(processed.shape[0], 150)
        self.assertEqual(processed.shape[1], 300)

    def test_document_upload_valid_image(self):
        self.client.login(username='usera', password='Password123!')
        upload_file = self._create_dummy_image('sample_doc.png')

        response = self.client.post(reverse('documents:upload'), {
            'title': 'Test Hand Note',
            'original_file': upload_file,
            'selected_language': 'en',
            'document_type': 'handwritten',
        })
        self.assertEqual(response.status_code, 302)
        doc = Document.objects.filter(user=self.user_a, title='Test Hand Note').first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.selected_language, 'en')
        self.assertEqual(doc.document_type, 'handwritten')
        self.assertEqual(doc.status, 'pending')

    def test_document_upload_invalid_extension(self):
        self.client.login(username='usera', password='Password123!')
        bad_file = SimpleUploadedFile("script.py", b"print('malicious')", content_type="text/x-python")

        response = self.client.post(reverse('documents:upload'), {
            'title': 'Bad File',
            'original_file': bad_file,
            'selected_language': 'en',
            'document_type': 'printed',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unsupported file format")
        self.assertFalse(Document.objects.filter(title='Bad File').exists())

    def test_document_ownership_isolation(self):
        # Create document for user A
        doc = Document.objects.create(
            user=self.user_a,
            title="User A Secret Notes",
            original_file=self._create_dummy_image(),
            original_filename="secret.png",
            selected_language='en'
        )

        # User B should NOT be able to view, edit or delete it
        self.client.login(username='userb', password='Password123!')
        detail_resp = self.client.get(reverse('documents:detail', kwargs={'pk': doc.pk}))
        self.assertEqual(detail_resp.status_code, 404)

        delete_resp = self.client.post(reverse('documents:delete', kwargs={'pk': doc.pk}))
        self.assertEqual(delete_resp.status_code, 404)

        # Document still exists
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())

    @patch('documents.services.easyocr_engine.EasyOCREngine.recognize')
    def test_ocr_processing_pipeline(self, mock_recognize):
        mock_recognize.return_value = {
            'text': 'Recognized Sample Text Line 1\nSecond Line',
            'confidence': 94.5,
            'duration': 0.45,
            'provider': 'easyocr'
        }

        doc = Document.objects.create(
            user=self.user_a,
            title="Telugu Script Document",
            original_file=self._create_dummy_image(),
            original_filename="telugu.png",
            selected_language='te',
            document_type='printed'
        )

        results = OCRService.process_document(
            document=doc,
            engine_id='easyocr',
            preprocessing_options={'apply_deskew': True, 'apply_clahe': True}
        )

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.page_number, 1)
        self.assertEqual(res.confidence, 94.5)
        self.assertEqual(res.original_recognized_text, 'Recognized Sample Text Line 1\nSecond Line')
        self.assertEqual(res.provider_name, 'easyocr')

        doc.refresh_from_db()
        self.assertEqual(doc.status, 'completed')
        self.assertTrue(doc.jobs.filter(status='completed').exists())

    def test_text_editing_preserves_original(self):
        doc = Document.objects.create(
            user=self.user_a,
            title="Editing Test",
            original_file=self._create_dummy_image(),
            original_filename="edit.png"
        )
        res = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Original Raw OCR Transcription with typoo",
            edited_text="Original Raw OCR Transcription with typoo",
            confidence=88.0,
            provider_name='easyocr'
        )

        self.client.login(username='usera', password='Password123!')
        response = self.client.post(reverse('documents:edit', kwargs={'pk': doc.pk}), {
            'page_number': 1,
            'edited_text': 'Original Raw OCR Transcription with corrected typo'
        })
        self.assertEqual(response.status_code, 302)

        res.refresh_from_db()
        self.assertEqual(res.edited_text, 'Original Raw OCR Transcription with corrected typo')
        # Crucial requirement: original OCR text MUST remain preserved
        self.assertEqual(res.original_recognized_text, 'Original Raw OCR Transcription with typoo')
        self.assertEqual(res.effective_text, 'Original Raw OCR Transcription with corrected typo')

    def test_all_export_formats(self):
        doc = Document.objects.create(
            user=self.user_a,
            title="Report Export Test",
            original_file=self._create_dummy_image(),
            original_filename="export.png",
            selected_language='en'
        )
        RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Antigravity Multilingual OCR Export Validation Text",
            edited_text="Antigravity Multilingual OCR Export Validation Text",
            confidence=95.0,
            provider_name='easyocr'
        )

        # 1. TXT Export
        txt_stream = ExportService.export_txt(doc)
        txt_content = txt_stream.getvalue().decode('utf-8')
        self.assertIn("DOCUMENT RECOGNITION TRANSCRIPT", txt_content)
        self.assertIn("Antigravity Multilingual OCR Export Validation Text", txt_content)

        # 2. CSV Export
        csv_stream = ExportService.export_csv(doc)
        csv_content = csv_stream.getvalue().decode('utf-8')
        self.assertIn("Document Title", csv_content)
        self.assertIn("Report Export Test", csv_content)

        # 3. DOCX Export
        docx_stream = ExportService.export_docx(doc)
        self.assertTrue(len(docx_stream.getvalue()) > 0)

        # 4. PDF Export
        pdf_stream = ExportService.export_pdf(doc)
        self.assertTrue(len(pdf_stream.getvalue()) > 0)
        self.assertTrue(pdf_stream.getvalue().startswith(b'%PDF-'))

    def test_document_deletion_cascades_and_cleans_files(self):
        doc = Document.objects.create(
            user=self.user_a,
            title="To Delete",
            original_file=self._create_dummy_image(),
            original_filename="del.png"
        )
        file_path = doc.original_file.path
        self.assertTrue(os.path.exists(file_path))

        # Delete document
        doc.delete()
        # Verify file is deleted on disk
        self.assertFalse(os.path.exists(file_path))

    def test_upload_file_stream_integrity(self):
        """Verifies BUG 1 fix: uploaded image file stream is not corrupted or duplicated."""
        upload_file = self._create_dummy_image('integrity_check.png', size=(100, 100))
        form = DocumentUploadForm(
            data={'title': 'Integrity Check', 'selected_language': 'en', 'document_type': 'printed'},
            files={'original_file': upload_file}
        )
        self.assertTrue(form.is_valid(), form.errors)
        cleaned_file = form.cleaned_data['original_file']
        # Read cleaned_file directly with PIL
        cleaned_file.seek(0)
        img = Image.open(cleaned_file)
        self.assertEqual(img.size, (100, 100))

    def test_ocr_safe_rerun_preserves_old_results_on_failure(self):
        """Verifies BUG 6 fix: OCR rerun failure does NOT delete existing results."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Safe Rerun Test",
            original_file=self._create_dummy_image(),
            original_filename="rerun.png",
            selected_language='en'
        )
        old_result = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Existing Good Result",
            edited_text="Existing Good Result",
            confidence=95.0,
            provider_name='easyocr'
        )

        with patch('documents.services.easyocr_engine.EasyOCREngine.recognize', side_effect=RuntimeError("OCR Engine Failure")):
            with self.assertRaises(RuntimeError):
                OCRService.process_document(
                    document=doc,
                    engine_id='easyocr',
                    preprocessing_options={}
                )

        # Existing result must STILL be in the database
        self.assertTrue(RecognitionResult.objects.filter(pk=old_result.pk).exists())
        reloaded = RecognitionResult.objects.get(pk=old_result.pk)
        self.assertEqual(reloaded.original_recognized_text, "Existing Good Result")

    def test_trocr_line_segmentation_includes_bottom_line(self):
        """Verifies BUG 2 fix: horizontal projection captures lines touching the bottom edge."""
        # Create a 200x200 white image with two black lines, one at the very bottom
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        # Line 1: rows 20 to 50
        img[20:50, 20:180] = 0
        # Line 2: rows 160 to 200 (touching the bottom edge)
        img[160:200, 20:180] = 0

        lines = TrOCREngine._segment_text_lines(img)
        self.assertGreaterEqual(len(lines), 2)

    def test_upload_empty_file_and_corrupted_header(self):
        """Verifies validation of empty files, corrupted images, and fake PDFs."""
        # 1. Empty file (0 bytes)
        empty_file = SimpleUploadedFile("empty.png", b"", content_type="image/png")
        form_empty = DocumentUploadForm(
            data={'title': 'Empty', 'selected_language': 'en', 'document_type': 'printed'},
            files={'original_file': empty_file}
        )
        self.assertFalse(form_empty.is_valid())
        self.assertIn("empty", str(form_empty.errors['original_file']))

        # 2. Corrupted image
        corrupted_file = SimpleUploadedFile("corrupted.png", b"NOT_A_VALID_PNG_DATA", content_type="image/png")
        form_corrupt = DocumentUploadForm(
            data={'title': 'Corrupted', 'selected_language': 'en', 'document_type': 'printed'},
            files={'original_file': corrupted_file}
        )
        self.assertFalse(form_corrupt.is_valid())
        self.assertIn("not a valid or readable image", str(form_corrupt.errors['original_file']))

        # 3. Fake PDF
        fake_pdf = SimpleUploadedFile("fake.pdf", b"NOT_A_REAL_PDF", content_type="application/pdf")
        form_fake_pdf = DocumentUploadForm(
            data={'title': 'Fake PDF', 'selected_language': 'en', 'document_type': 'printed'},
            files={'original_file': fake_pdf}
        )
        self.assertFalse(form_fake_pdf.is_valid())
        self.assertIn("Invalid PDF file structure", str(form_fake_pdf.errors['original_file']))

    def test_pdf_service_error_handling(self):
        """Verifies PDFService handles non-existent and malformed PDFs safely."""
        with self.assertRaises(FileNotFoundError):
            PDFService.get_page_count("C:/non_existent_path/dummy.pdf")

        with self.assertRaises(FileNotFoundError):
            PDFService.render_pages_to_images("C:/non_existent_path/dummy.pdf")

        # Test malformed file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(b"GARBAGE_NON_PDF_DATA")
            tmp_path = tmp.name

        try:
            with self.assertRaises(ValueError):
                PDFService.get_page_count(tmp_path)
            with self.assertRaises(RuntimeError):
                PDFService.render_pages_to_images(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_easyocr_reading_order_grouping(self):
        """Verifies that bounding boxes are grouped into lines and sorted top-to-bottom, left-to-right."""
        # Mock easyocr.Reader.readtext returning boxes out of reading order
        # Box format: ([[x1, y1], [x2, y2], [x3, y3], [x4, y4]], "text", confidence)
        mock_boxes = [
            # Line 2: y around 60
            ([[10, 55], [100, 55], [100, 75], [10, 75]], "World", 0.95),
            # Line 1, word 2: x=120, y around 20
            ([[120, 15], [200, 15], [200, 35], [120, 35]], "Beautiful", 0.92),
            # Line 1, word 1: x=10, y around 20
            ([[10, 15], [100, 15], [100, 35], [10, 35]], "Hello", 0.98),
        ]

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = mock_boxes
        with patch.object(EasyOCREngine, 'get_reader', return_value=mock_reader):
            dummy_img = np.ones((100, 250, 3), dtype=np.uint8) * 255
            result = EasyOCREngine.recognize(dummy_img, language_code='en', document_type='printed')

            # Expect Line 1: "Hello Beautiful", Line 2: "World"
            expected_text = "Hello Beautiful\nWorld"
            self.assertEqual(result['text'], expected_text)
            self.assertEqual(result['line_count'], 2)
            self.assertGreater(result['confidence'], 90.0)

    def test_trocr_empty_image_handling(self):
        """Verifies TrOCR engine handles empty or 0-dimension images gracefully."""
        empty_img = np.zeros((0, 0, 3), dtype=np.uint8)
        lines = TrOCREngine._segment_text_lines(empty_img)
        self.assertEqual(len(lines), 0)

        res = TrOCREngine.recognize(empty_img, language_code='en')
        self.assertEqual(res['text'], '')
        self.assertEqual(res['confidence'], 0.0)
        self.assertEqual(res['line_count'], 0)

    def test_google_vision_missing_credentials_raises_runtime_error(self):
        """Verifies Google Cloud Vision raises a helpful error when credentials are not configured."""
        with patch.object(GoogleVisionEngine, 'is_configured', return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                GoogleVisionEngine.recognize("dummy.png", language_code='en')
            self.assertIn("Google Cloud Vision is not configured", str(ctx.exception))

    def test_translation_service_validations(self):
        """Verifies TranslationService input parameter and language validations."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Translation Test",
            original_file=self._create_dummy_image(),
            selected_language='en'
        )
        res = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Hello World",
            edited_text="Hello World",
            confidence=95.0,
            provider_name='easyocr'
        )

        # 1. Missing target language
        with self.assertRaises(ValueError) as ctx:
            TranslationService.translate_result(res, target_language='')
        self.assertIn("Target language must be specified", str(ctx.exception))

        # 2. Identical source and target language
        with self.assertRaises(ValueError) as ctx:
            TranslationService.translate_result(res, target_language='en', source_language='en')
        self.assertIn("Source and target languages cannot be identical", str(ctx.exception))

        # 3. Empty text to translate
        empty_res = RecognitionResult.objects.create(
            document=doc,
            page_number=2,
            original_recognized_text="",
            edited_text="",
            confidence=0.0,
            provider_name='easyocr'
        )
        with self.assertRaises(ValueError) as ctx:
            TranslationService.translate_result(empty_res, target_language='te')
        self.assertIn("No text available to translate", str(ctx.exception))

    def test_recognize_view_unauthenticated_and_incompatible(self):
        """Verifies access control and compatibility validation on the recognize view."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Telugu Note",
            original_file=self._create_dummy_image(),
            selected_language='te',
            document_type='handwritten'
        )

        # 1. Unauthenticated user must be redirected to login
        response = self.client.get(reverse('documents:recognize', kwargs={'pk': doc.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

        # 2. Authenticated user selects incompatible engine (TrOCR for Telugu)
        self.client.login(username='usera', password='Password123!')
        post_resp = self.client.post(reverse('documents:recognize', kwargs={'pk': doc.pk}), {
            'engine': 'trocr',
            'apply_deskew': True,
        })
        self.assertEqual(post_resp.status_code, 200)
        # Form should be invalid and render error in page
        self.assertContains(post_resp, "does not support Telugu")

    def test_document_upload_form_renders_language_choices(self):
        """Verifies DocumentUploadForm populates both field and widget choices."""
        form = DocumentUploadForm()
        # Field choices must contain all registered languages
        self.assertGreaterEqual(len(form.fields['selected_language'].choices), 10)
        # Widget choices must also be populated so HTML <option> tags render
        self.assertGreaterEqual(len(form.fields['selected_language'].widget.choices), 10)
        rendered_html = form['selected_language'].as_widget()
        self.assertIn('<option value="en"', rendered_html)
        self.assertIn('<option value="te"', rendered_html)
        self.assertIn('<option value="hi"', rendered_html)

    def test_upload_page_html_renders_option_elements(self):
        """Verifies GET /documents/upload/ renders HTML <option> elements for languages."""
        self.client.login(username='usera', password='Password123!')
        response = self.client.get(reverse('documents:upload'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="languageSelect"')
        self.assertContains(response, '<option value="en"')
        self.assertContains(response, '<option value="te"')
        self.assertContains(response, '<option value="hi"')

    def test_document_upload_valid_language_submission(self):
        """Verifies submitting a valid language script saves correctly on the document."""
        self.client.login(username='usera', password='Password123!')
        upload_file = self._create_dummy_image('telugu_note.png')

        response = self.client.post(reverse('documents:upload'), {
            'title': 'Telugu Hand Note',
            'original_file': upload_file,
            'selected_language': 'te',
            'document_type': 'handwritten',
        })
        self.assertEqual(response.status_code, 302)
        doc = Document.objects.filter(user=self.user_a, title='Telugu Hand Note').first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.selected_language, 'te')
        self.assertEqual(doc.document_type, 'handwritten')
        self.assertRedirects(response, reverse('documents:recognize', kwargs={'pk': doc.pk}))

    def test_document_upload_missing_language_validation_error(self):
        """Verifies missing selected_language fails validation and renders field error."""
        self.client.login(username='usera', password='Password123!')
        upload_file = self._create_dummy_image('sample.png')

        response = self.client.post(reverse('documents:upload'), {
            'title': 'No Language Note',
            'original_file': upload_file,
            'document_type': 'handwritten',
            # selected_language omitted
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('selected_language', form.errors)
        self.assertFalse(Document.objects.filter(title='No Language Note').exists())

    def test_document_upload_valid_jpeg_single_record(self):
        """Verifies uploading a JPEG file creates exactly one document record."""
        self.client.login(username='usera', password='Password123!')
        upload_file = self._create_dummy_jpeg('receipt.jpg')

        initial_count = Document.objects.filter(user=self.user_a).count()
        response = self.client.post(reverse('documents:upload'), {
            'title': 'Test JPEG Note',
            'original_file': upload_file,
            'selected_language': 'en',
            'document_type': 'printed',
        })
        self.assertEqual(response.status_code, 302)
        final_count = Document.objects.filter(user=self.user_a).count()
        self.assertEqual(final_count, initial_count + 1)
        doc = Document.objects.filter(user=self.user_a, title='Test JPEG Note').first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.original_filename, 'receipt.jpg')

    @patch('documents.services.easyocr_engine.EasyOCREngine.recognize')
    def test_recognition_flow_end_to_end_with_results_page(self, mock_recognize):
        """Verifies complete recognition flow from upload to recognize post to results view."""
        mock_recognize.return_value = {
            'text': 'Recognized End-to-End Handwritten Content',
            'confidence': 91.2,
            'duration': 0.35,
            'provider': 'easyocr'
        }
        self.client.login(username='usera', password='Password123!')
        upload_file = self._create_dummy_image('pipeline_test.png')

        # 1. Upload
        upload_resp = self.client.post(reverse('documents:upload'), {
            'title': 'End to End Doc',
            'original_file': upload_file,
            'selected_language': 'en',
            'document_type': 'handwritten',
        })
        doc = Document.objects.get(user=self.user_a, title='End to End Doc')
        self.assertRedirects(upload_resp, reverse('documents:recognize', kwargs={'pk': doc.pk}))

        # 2. Get Recognize Page
        rec_get_resp = self.client.get(reverse('documents:recognize', kwargs={'pk': doc.pk}))
        self.assertEqual(rec_get_resp.status_code, 200)
        self.assertContains(rec_get_resp, 'End to End Doc')

        # 3. Post Recognition Config
        rec_post_resp = self.client.post(reverse('documents:recognize', kwargs={'pk': doc.pk}), {
            'engine': 'easyocr',
            'apply_deskew': True,
            'apply_clahe': True,
        })
        self.assertRedirects(rec_post_resp, reverse('documents:results', kwargs={'pk': doc.pk}))

        # 4. View Results
        results_resp = self.client.get(reverse('documents:results', kwargs={'pk': doc.pk}))
        self.assertEqual(results_resp.status_code, 200)
        self.assertContains(results_resp, 'Recognized End-to-End Handwritten Content')
        self.assertContains(results_resp, '91.2% Confidence')

    def test_recognition_failure_job_status_and_user_message(self):
        """Verifies failed recognition updates job status to failed and displays error message."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Failing Doc",
            original_file=self._create_dummy_image('fail.png'),
            selected_language='en',
            document_type='printed'
        )
        self.client.login(username='usera', password='Password123!')

        with patch('documents.services.easyocr_engine.EasyOCREngine.recognize', side_effect=RuntimeError("OCR Internal Processing Error")):
            rec_resp = self.client.post(reverse('documents:recognize', kwargs={'pk': doc.pk}), {
                'engine': 'easyocr',
            }, follow=True)
            self.assertEqual(rec_resp.status_code, 200)
            self.assertContains(rec_resp, "Recognition failed: OCR Internal Processing Error")

            # Check that job status recorded failure
            job = RecognitionJob.objects.filter(document=doc).last()
            self.assertIsNotNone(job)
            self.assertEqual(job.status, 'failed')
            self.assertIn("OCR Internal Processing Error", job.safe_error_message)

    def test_medical_prescription_extractor(self):
        """Verifies MedicalPrescriptionExtractor on empty and prescription transcripts."""
        # 1. Empty transcript
        empty_res = MedicalPrescriptionExtractor.extract("")
        self.assertEqual(empty_res['status'], 'empty')
        self.assertIn('disclaimer', empty_res)
        self.assertEqual(len(empty_res['medications']), 0)

        # 2. Prescription text
        sample_rx = (
            "Dr. Rajesh Kumar MBBS MD\n"
            "Date: 12/10/2026\n"
            "Patient: John Doe, Age 45\n"
            "Rx:\n"
            "1. Tab Amoxicillin 500mg TID after meals for 5 days\n"
            "2. Paracetamol 650mg SOS"
        )
        rx_data = MedicalPrescriptionExtractor.extract(sample_rx)
        self.assertIsNotNone(rx_data)
        self.assertGreater(len(rx_data['medications']), 0)
        self.assertTrue(any('Amoxicillin' in m['medicine_name'] for m in rx_data['medications']))

    def test_bank_record_extractor(self):
        """Verifies BankRecordExtractor on account masking and financial statements."""
        # 1. Account number masking
        masked = BankRecordExtractor.mask_account_number("123456789012")
        self.assertTrue(masked.endswith("9012"))
        self.assertIn("X", masked)

        # 2. Bank statement text
        statement = (
            "State Bank of India\n"
            "Account Number: 123456789012\n"
            "Statement Date: 15/10/2026\n"
            "10/10/2026 Deposit Salary ₹50,000.00\n"
            "12/10/2026 Withdrawal Rent ₹15,000.00"
        )
        bank_data = BankRecordExtractor.extract(statement)
        self.assertIsNotNone(bank_data)
        self.assertEqual(bank_data['bank_name'], 'State Bank of India')
        self.assertTrue(bank_data['account_number_masked'].endswith('9012'))

    def test_translation_workflow_persistence_and_export(self):
        """Verifies TranslationService translates, persists, and exports as TXT."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Translation Persistence Test",
            original_file=self._create_dummy_image(),
            selected_language='en',
            document_type='handwritten'
        )
        res = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Priority interrupt polling system and device hardware.",
            edited_text="Priority interrupt polling system and device hardware.",
            confidence=85.0,
            provider_name='easyocr'
        )

        # 1. Translate to Telugu
        trans = TranslationService.translate_result(res, target_language='te')
        self.assertIsNotNone(trans)
        self.assertEqual(trans.target_language, 'te')
        self.assertTrue(len(trans.translated_text) > 0)
        self.assertEqual(trans.status, 'completed')

        # 2. Check record exists in database
        self.assertTrue(TranslationResult.objects.filter(pk=trans.pk).exists())

        # 3. Export Translation TXT
        self.client.login(username='usera', password='Password123!')
        export_resp = self.client.get(reverse('documents:export_trans_txt', kwargs={'pk': doc.pk}))
        self.assertEqual(export_resp.status_code, 200)
        self.assertIn('text/plain', export_resp['Content-Type'])
        self.assertIn('attachment', export_resp['Content-Disposition'])
        content = export_resp.content.decode('utf-8')
        self.assertIn("DOCUMENT TRANSLATION REPORT", content)
        self.assertIn("TE", content)

    def test_translation_ajax_json_endpoint(self):
        """Verifies AJAX JSON response from DocumentTranslateView."""
        doc = Document.objects.create(
            user=self.user_a,
            title="AJAX Translation Test",
            original_file=self._create_dummy_image(),
            selected_language='en'
        )
        res = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Doctor prescribed medicine for patient.",
            confidence=90.0,
            provider_name='easyocr'
        )

        self.client.login(username='usera', password='Password123!')
        response = self.client.post(
            reverse('documents:translate', kwargs={'pk': doc.pk}),
            {'target_language': 'hi', 'page_number': 1},
            headers={'x-requested-with': 'XMLHttpRequest'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('target_language'), 'HI')
        self.assertTrue(len(data.get('translated_text', '')) > 0)

    def test_human_assisted_correction_and_status_tracking(self):
        """Verifies manual editing sets status_tracking to manually_edited and updates structured data."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Prescription Note",
            original_file=self._create_dummy_image(),
            selected_language='en',
            document_type='medical'
        )
        res = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="Dr. Alice Smith\n1. Paracetamol 500mg BD for 3 days",
            edited_text="Dr. Alice Smith\n1. Paracetamol 500mg BD for 3 days",
            confidence=82.0,
            provider_name='easyocr',
            status_tracking='raw'
        )

        self.client.login(username='usera', password='Password123!')
        # User manually corrects a typo
        edit_resp = self.client.post(reverse('documents:edit', kwargs={'pk': doc.pk}), {
            'page_number': 1,
            'edited_text': "Dr. Alice Smith\n1. Paracetamol 650mg BD for 5 days"
        })
        self.assertEqual(edit_resp.status_code, 302)

        res.refresh_from_db()
        self.assertEqual(res.status_tracking, 'manually_edited')
        # Original raw OCR must remain untouched
        self.assertEqual(res.original_recognized_text, "Dr. Alice Smith\n1. Paracetamol 500mg BD for 3 days")
        self.assertEqual(res.effective_text, "Dr. Alice Smith\n1. Paracetamol 650mg BD for 5 days")
        # Structured data was refreshed with edited dosage/duration
        self.assertIsNotNone(res.structured_data)
        self.assertTrue(any('650mg' in m.get('dosage', '') for m in res.structured_data.get('medications', [])))

    def test_results_view_renders_structured_panels(self):
        """Verifies results page renders structured review cards and confidence inspection."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Bank Statement Doc",
            original_file=self._create_dummy_image(),
            selected_language='en',
            document_type='bank'
        )
        res = RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text="State Bank of India\nAccount Number: 123456789012\n10/10/2026 Deposit ₹5,000.00",
            confidence=75.0,
            confidence_details=[{
                'line_number': 1,
                'text': 'State Bank of India',
                'confidence': 75.0,
                'words': [{'word': 'State', 'confidence': 55.0, 'is_low_confidence': True}]
            }],
            structured_data={
                'bank_name': 'State Bank of India',
                'account_number_masked': 'XXXX-XXXX-9012',
                'arithmetic_balanced': True,
                'currency': 'INR',
                'transactions': []
            },
            provider_name='easyocr'
        )

        self.client.login(username='usera', password='Password123!')
        response = self.client.get(reverse('documents:results', kwargs={'pk': doc.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bank Statement & Transaction Review')
        self.assertContains(response, 'XXXX-XXXX-9012')
        self.assertContains(response, 'Inspect Uncertain Words')

    def test_preprocessing_illumination_normalization(self):
        """Verifies illumination normalization flattens lighting on gradient test image."""
        # Create gradient image (simulating shadow across page)
        gradient = np.tile(np.linspace(50, 255, 300, dtype=np.uint8), (150, 1))
        norm = PreprocessingPipeline.normalize_illumination(gradient, kernel_size=31)
        self.assertEqual(norm.shape, gradient.shape)
        # Normalized image has higher minimum brightness than raw dark shadow area
        self.assertGreater(norm.mean(), gradient.mean())

    def test_technical_postprocessor_code_preservation(self):
        """Verifies programming syntax (brackets, underscores, semicolons) is strictly preserved and formatted."""
        noisy_code = (
            "if (device [0]_floq)\n"
            "Aeviceto] seruiceU;\n"
            "else ik [device ((],ftaq)"
        )
        cleaned = TechnicalPostProcessor.post_process(noisy_code)
        self.assertIn("if (device[0]_flag)", cleaned)
        self.assertIn("device[0].service();", cleaned)
        self.assertIn("else if (device[1].flag)", cleaned)

    def test_technical_postprocessor_terminology_refinement(self):
        """Verifies domain misrecognitions in computer architecture lecture notes are normalized."""
        noisy_prose = (
            "Prfoxity Tnl-errupt pollinq and\n"
            "Dausychaling els\n"
            "Softuare method ~(poltinq)\n"
            "Pblling is a Slvo baled Intexuput Interrupt bndlirg method\n"
            "firse deaded 64 the hotidtate Prtonily 8s not\n"
            "be in waiting gtate"
        )
        cleaned = TechnicalPostProcessor.post_process(noisy_prose)
        self.assertIn("Priority", cleaned)
        self.assertIn("interrupt", cleaned.lower())
        self.assertIn("polling", cleaned.lower())
        self.assertIn("daisychaining", cleaned.lower())
        self.assertIn("S/W", cleaned)
        self.assertIn("hardware", cleaned.lower())
        self.assertIn("waiting state", cleaned.lower())

    def test_easyocr_reading_order_and_line_clustering(self):
        """Verifies reading order does not split handwritten sentences across the page into disjoint columns."""
        # Mock OCR output: 3 bounding boxes forming one continuous handwritten sentence
        # Word 1: left, Word 2: middle, Word 3: right (all sharing overlapping vertical y=100-140)
        mock_results = [
            ([[50, 100], [200, 100], [200, 140], [50, 140]], "Priority Interrupt", 0.85),
            ([[220, 105], [450, 105], [450, 145], [220, 145]], "Polling and", 0.78),
            ([[470, 102], [700, 102], [700, 142], [470, 142]], "Daisychaining", 0.82),
        ]
        with patch.object(EasyOCREngine, 'get_reader') as mock_reader_cls:
            mock_reader = MagicMock()
            mock_reader.readtext.return_value = mock_results
            mock_reader_cls.return_value = mock_reader

            dummy_img = np.ones((500, 800, 3), dtype=np.uint8) * 255
            res = EasyOCREngine.recognize(dummy_img, language_code='en', document_type='handwritten')
            
            # Words should be grouped into a single unified line in left-to-right order
            self.assertEqual(res['line_count'], 1)
            self.assertIn("Priority Interrupt Polling and Daisychaining", res['text'])
            self.assertGreater(res['confidence'], 80.0)

    def test_accuracy_evaluation_benchmark_metrics(self):
        """Verifies CER and WER calculations work accurately using Levenshtein distance."""
        ref = "Priority Interrupt: Polling and Daisychaining"
        hyp_exact = "Priority Interrupt: Polling and Daisychaining"
        hyp_err = "Priority Interrupt: Polling and daisychaining"

        self.assertEqual(calculate_cer(ref, hyp_exact), 0.0)
        self.assertEqual(calculate_wer(ref, hyp_exact), 0.0)

        cer = calculate_cer(ref, hyp_err)
        wer = calculate_wer(ref, hyp_err)
        self.assertLess(cer, 0.05)
        self.assertLess(wer, 0.25)

    def test_translation_six_language_pairs(self):
        """Verifies bidirectional translation across all 6 pairs: EN<->TE, EN<->HI, TE<->HI."""
        pairs = [
            ('en', 'te', "Priority interrupt polling system and device hardware."),
            ('en', 'hi', "Priority interrupt polling system and device hardware."),
            ('te', 'en', "ప్రాధాన్యత అంతరాయం పోలింగ్ మరియు హార్డ్‌వేర్ పరికరం."),
            ('te', 'hi', "ప్రాధాన్యత అంతరాయం పోలింగ్ వ్యవస్థ."),
            ('hi', 'en', "प्राथमिकता व्यवधान पोलिंग प्रणाली और हार्डवेयर डिवाइस।"),
            ('hi', 'te', "प्राथमिकता व्यवधान पोलिंग प्रणाली।"),
        ]
        for src, tgt, sample_text in pairs:
            res_text, provider = TranslationService.translate_text(
                sample_text,
                target_language=tgt,
                source_language=src
            )
            self.assertTrue(len(res_text.strip()) > 0, f"Empty result for {src}->{tgt}")
            self.assertIsNotNone(provider)

    def test_export_service_indic_unicode_pdf_and_docx(self):
        """Verifies PDF and DOCX export with Telugu, Hindi, and English Unicode glyphs."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Multilingual Export Test",
            original_file=self._create_dummy_image(),
            selected_language='te',
            document_type='academic'
        )
        multilingual_content = (
            "English: Priority Interrupt\n"
            "Telugu: ప్రాధాన్యత అంతరాయం పోలింగ్ పద్ధతి\n"
            "Hindi: प्राथमिकता व्यवधान पोलिंग विधि"
        )
        RecognitionResult.objects.create(
            document=doc,
            page_number=1,
            original_recognized_text=multilingual_content,
            edited_text=multilingual_content,
            confidence=94.5,
            provider_name='easyocr'
        )

        # 1. PDF Export
        pdf_io = ExportService.export_pdf(doc)
        pdf_bytes = pdf_io.getvalue()
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 100)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

        # 2. DOCX Export
        docx_io = ExportService.export_docx(doc)
        docx_bytes = docx_io.getvalue()
        self.assertIsInstance(docx_bytes, bytes)
        self.assertGreater(len(docx_bytes), 100)
        self.assertTrue(docx_bytes.startswith(b'PK'))

    def test_recognition_config_document_type_switching(self):
        """Verifies changing document_type during recognition reclassifies the document."""
        doc = Document.objects.create(
            user=self.user_a,
            title="Lecture Notes Doc",
            original_file=self._create_dummy_image('notes.png'),
            selected_language='en',
            document_type='printed'
        )
        self.client.login(username='usera', password='Password123!')

        with patch('documents.services.easyocr_engine.EasyOCREngine.recognize') as mock_rec:
            mock_rec.return_value = {
                'text': 'Priority Interrupt',
                'confidence': 92.0,
                'duration': 0.5,
                'provider': 'easyocr'
            }
            resp = self.client.post(reverse('documents:recognize', kwargs={'pk': doc.pk}), {
                'engine': 'easyocr',
                'document_type': 'academic',
            })
            self.assertEqual(resp.status_code, 302)

            doc.refresh_from_db()
            self.assertEqual(doc.document_type, 'academic')
