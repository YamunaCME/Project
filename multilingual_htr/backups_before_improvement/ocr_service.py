"""
Unified OCR and HTR Orchestration Service.

Coordinates document preprocessing, page extraction for PDFs,
engine dispatching, and persistence of results and execution jobs.
"""

import os
import time
from typing import Dict, Any, List
from django.utils import timezone
from django.conf import settings
from django.db import transaction

from documents.models import Document, RecognitionResult, RecognitionJob
from .language_registry import LanguageRegistry
from .preprocessing import PreprocessingPipeline
from .pdf_service import PDFService
from .easyocr_engine import EasyOCREngine
from .trocr_engine import TrOCREngine
from .google_vision_engine import GoogleVisionEngine
from .medical_extractor import MedicalPrescriptionExtractor
from .bank_extractor import BankRecordExtractor


class OCRService:
    @staticmethod
    def get_engine_implementation(engine_id: str):
        """Returns the appropriate engine runner class."""
        engine_id = engine_id.lower().strip()
        if engine_id == 'easyocr':
            return EasyOCREngine
        elif engine_id == 'trocr':
            return TrOCREngine
        elif engine_id == 'google_vision':
            return GoogleVisionEngine
        else:
            raise ValueError(f"Unsupported OCR engine ID '{engine_id}'.")

    @staticmethod
    def _run_recognition(engine_cls, image_input, language_code: str, document_type: str = 'printed') -> Dict[str, Any]:
        """Safely invokes engine recognize method with or without document_type parameter."""
        try:
            return engine_cls.recognize(
                image_input=image_input,
                language_code=language_code,
                document_type=document_type
            )
        except TypeError:
            return engine_cls.recognize(
                image_input=image_input,
                language_code=language_code
            )

    @classmethod
    def process_document(
        cls,
        document: Document,
        engine_id: str,
        preprocessing_options: Dict[str, Any]
    ) -> List[RecognitionResult]:
        """
        Executes the full recognition pipeline for a document.
        Handles both single-page image files and multi-page PDFs.
        """
        # 1. Compatibility check
        is_compatible, reason = LanguageRegistry.is_engine_compatible(
            engine_id=engine_id,
            language_code=document.selected_language,
            document_type=document.document_type
        )
        if not is_compatible:
            raise ValueError(reason)

        engine_cls = cls.get_engine_implementation(engine_id)

        # 2. Initialize tracking job
        job = RecognitionJob.objects.create(
            document=document,
            status='running',
            started_at=timezone.now()
        )
        document.status = 'processing'
        document.save(update_fields=['status'])

        # Staged results list: preserve previous results until all pages succeed (BUG 6 fix)
        staged_results: List[Dict[str, Any]] = []
        preview_rel_path = None
        new_page_count = 1
        is_truncated = False
        total_pages = 1

        try:
            file_path = document.original_file.path

            if document.is_pdf:
                # PDF processing: render pages with page limit awareness (BUG 8 fix)
                pages, total_pages, is_truncated = PDFService.render_pages_to_images(
                    pdf_path=file_path,
                    max_pages=settings.MAX_PDF_PAGES,
                    dpi=300,
                    return_meta=True
                )
                new_page_count = len(pages)

                for page_num, pil_image in pages:
                    preview_dir = os.path.join(settings.MEDIA_ROOT, 'preprocessed', str(document.id))
                    preview_path = os.path.join(preview_dir, f"page_{page_num}.jpg")

                    preprocessed_arr, saved_preview = PreprocessingPipeline.apply(
                        pil_image,
                        options=preprocessing_options,
                        save_path=preview_path
                    )

                    if page_num == 1 and saved_preview:
                        preview_rel_path = os.path.relpath(saved_preview, settings.MEDIA_ROOT).replace('\\', '/')

                    # Run recognition with document_type context
                    res_dict = cls._run_recognition(
                        engine_cls=engine_cls,
                        image_input=preprocessed_arr,
                        language_code=document.selected_language,
                        document_type=document.document_type
                    )

                    raw_text = res_dict.get('raw_text') or res_dict.get('text', '')
                    cleaned_text = res_dict.get('text', '')

                    staged_results.append({
                        'page_number': page_num,
                        'original_recognized_text': raw_text,
                        'edited_text': cleaned_text,
                        'confidence': res_dict.get('confidence'),
                        'processing_duration': res_dict.get('duration', 0.0),
                        'provider_name': engine_id,
                        'confidence_details': res_dict.get('confidence_details', []),
                    })

            else:
                # Single Image Document processing
                new_page_count = 1
                preview_dir = os.path.join(settings.MEDIA_ROOT, 'preprocessed', str(document.id))
                preview_path = os.path.join(preview_dir, "preview.jpg")

                preprocessed_arr, saved_preview = PreprocessingPipeline.apply(
                    file_path,
                    options=preprocessing_options,
                    save_path=preview_path
                )

                if saved_preview:
                    preview_rel_path = os.path.relpath(saved_preview, settings.MEDIA_ROOT).replace('\\', '/')

                # Run recognition with document_type context
                res_dict = cls._run_recognition(
                    engine_cls=engine_cls,
                    image_input=preprocessed_arr,
                    language_code=document.selected_language,
                    document_type=document.document_type
                )

                raw_text = res_dict.get('raw_text') or res_dict.get('text', '')
                cleaned_text = res_dict.get('text', '')

                staged_results.append({
                    'page_number': 1,
                    'original_recognized_text': raw_text,
                    'edited_text': cleaned_text,
                    'confidence': res_dict.get('confidence'),
                    'processing_duration': res_dict.get('duration', 0.0),
                    'provider_name': engine_id,
                    'confidence_details': res_dict.get('confidence_details', []),
                })

            # Atomic transaction: only replace old results once new run completes entirely
            with transaction.atomic():
                document.results.all().delete()
                created_results: List[RecognitionResult] = []
                for item in staged_results:
                    structured_data = {}
                    if document.document_type == 'medical':
                        structured_data = MedicalPrescriptionExtractor.extract(
                            transcript=item['original_recognized_text'],
                            confidence_details=item.get('confidence_details', [])
                        )
                    elif document.document_type in ('bank', 'financial'):
                        structured_data = BankRecordExtractor.extract(
                            transcript=item['original_recognized_text'],
                            confidence_details=item.get('confidence_details', [])
                        )

                    has_processing = bool(item['edited_text'] and item['edited_text'] != item['original_recognized_text'])
                    res_obj = RecognitionResult.objects.create(
                        document=document,
                        page_number=item['page_number'],
                        original_recognized_text=item['original_recognized_text'],
                        edited_text=item['edited_text'],
                        confidence=item['confidence'],
                        processing_duration=item['processing_duration'],
                        provider_name=item['provider_name'],
                        confidence_details=item.get('confidence_details', []),
                        structured_data=structured_data,
                        status_tracking='processed' if has_processing else 'raw'
                    )
                    created_results.append(res_obj)

                if preview_rel_path:
                    document.processed_file.name = preview_rel_path

                document.page_count = new_page_count
                document.status = 'completed'
                document.save(update_fields=['page_count', 'status', 'processed_file'])

                job.status = 'completed'
                job.completed_at = timezone.now()
                if is_truncated:
                    job.safe_error_code = 'PAGE_LIMIT_REACHED'
                    job.safe_error_message = f"Processed {new_page_count} of {total_pages} pages (max limit: {settings.MAX_PDF_PAGES})."
                job.save()

            return created_results

        except Exception as e:
            job.status = 'failed'
            job.completed_at = timezone.now()
            job.safe_error_code = type(e).__name__
            job.safe_error_message = str(e)
            job.save()

            # Preserve completed status if previous results exist, else mark failed
            if not document.results.exists():
                document.status = 'failed'
                document.save(update_fields=['status'])
            raise
