import os
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Document, RecognitionResult, RecognitionJob, TranslationResult
from .forms import DocumentUploadForm, RecognitionConfigForm, DocumentEditForm, TranslationForm
from .services.ocr_service import OCRService
from .services.language_registry import LanguageRegistry
from .services.export_service import ExportService
from .services.translation_service import TranslationService
from .services.medical_extractor import MedicalPrescriptionExtractor
from .services.bank_extractor import BankRecordExtractor
from .services.evaluation_service import EvaluationService, compute_metrics


class HomeView(TemplateView):
    template_name = 'home.html'

class DocumentUploadView(LoginRequiredMixin, View):
    def get(self, request):
        form = DocumentUploadForm()
        return render(request, 'documents/upload.html', {'form': form})

    def post(self, request):
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            doc = form.save(commit=False)
            doc.user = request.user
            doc.original_filename = request.FILES['original_file'].name
            doc.file_size = request.FILES['original_file'].size

            # Intelligent category hint if default 'printed' was submitted
            fname_lower = doc.original_filename.lower()
            if doc.document_type == 'printed':
                if any(k in fname_lower for k in ['rx', 'prescription', 'med', 'doctor', 'hospital']):
                    doc.document_type = 'medical'
                elif any(k in fname_lower for k in ['bank', 'stmt', 'statement', 'transaction', 'invoice', 'receipt']):
                    doc.document_type = 'bank'
                elif any(k in fname_lower for k in ['note', 'lecture', 'hw', 'assignment', '2nd', 'handwritten', 'notes']):
                    doc.document_type = 'academic'

            doc.save()

            messages.success(
                request,
                f"Document '{doc.title}' uploaded successfully! "
                "Select your recognition options below."
            )
            return redirect('documents:recognize', pk=doc.pk)

        return render(request, 'documents/upload.html', {'form': form})
class DocumentListView(LoginRequiredMixin, ListView):
    """Document archive/history with search, filtering, and pagination."""
    model = Document
    template_name = 'documents/history.html'
    context_object_name = 'documents'
    paginate_by = 10

    def get_queryset(self):
        qs = Document.objects.filter(user=self.request.user)

        # Search by title or filename
        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(original_filename__icontains=query))

        # Status filter
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        # Language filter
        lang = self.request.GET.get('language', '').strip()
        if lang:
            qs = qs.filter(selected_language=lang)

        # Document type filter
        doc_type = self.request.GET.get('type', '').strip()
        if doc_type:
            qs = qs.filter(document_type=doc_type)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_lang'] = self.request.GET.get('language', '')
        context['selected_type'] = self.request.GET.get('type', '')
        context['status_choices'] = Document.STATUS_CHOICES
        context['languages'] = LanguageRegistry.get_all_languages()
        context['type_choices'] = Document.DOCUMENT_TYPE_CHOICES
        return context


class DocumentDetailView(LoginRequiredMixin, DetailView):
    model = Document
    template_name = 'documents/detail.html'
    context_object_name = 'document'

    def get_object(self, queryset=None):
        doc = super().get_object(queryset)
        if doc.user != self.request.user and not self.request.user.is_staff:
            raise Http404("Document not found.")
        return doc


class DocumentRecognizeView(LoginRequiredMixin, View):
    """Recognition page: previews document, checks capability, and executes OCR."""
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        form = RecognitionConfigForm(document=doc)
        compatible_engines = LanguageRegistry.get_compatible_engines(
            language_code=doc.selected_language,
            document_type=doc.document_type
        )
        return render(request, 'documents/recognize.html', {
            'document': doc,
            'form': form,
            'compatible_engines': compatible_engines,
            'all_engines': LanguageRegistry.get_available_engines(),
        })

    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        form = RecognitionConfigForm(request.POST, document=doc)

        if form.is_valid():
            engine = form.cleaned_data['engine']
            new_doc_type = form.cleaned_data.get('document_type')
            if new_doc_type and new_doc_type != doc.document_type:
                doc.document_type = new_doc_type
                doc.save(update_fields=['document_type'])

            options = {
                'apply_deskew': form.cleaned_data.get('apply_deskew', True),
                'apply_illumination': form.cleaned_data.get('apply_illumination', True),
                'apply_clahe': form.cleaned_data.get('apply_clahe', True),
                'apply_sharpening': form.cleaned_data.get('apply_sharpening', True),
                'apply_denoising': form.cleaned_data.get('apply_denoising', False),
                'apply_threshold': form.cleaned_data.get('apply_threshold', False),
            }

            try:
                OCRService.process_document(
                    document=doc,
                    engine_id=engine,
                    preprocessing_options=options
                )
                messages.success(request, f"Recognition completed successfully using {engine.upper()}!")
                return redirect('documents:results', pk=doc.pk)
            except Exception as e:
                messages.error(request, f"Recognition failed: {str(e)}")
                return redirect('documents:recognize', pk=doc.pk)

        compatible_engines = LanguageRegistry.get_compatible_engines(
            language_code=doc.selected_language,
            document_type=doc.document_type
        )
        return render(request, 'documents/recognize.html', {
            'document': doc,
            'form': form,
            'compatible_engines': compatible_engines,
            'all_engines': LanguageRegistry.get_available_engines(),
        })


class DocumentResultsView(LoginRequiredMixin, View):
    """Displays recognition output, confidence stats, and export shortcuts."""
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        results = doc.results.all().order_by('page_number')

        # Current page tab selection for multi-page documents
        page_num = int(request.GET.get('page', 1))
        current_result = results.filter(page_number=page_num).first() or results.first()

        edit_form = DocumentEditForm(instance=current_result) if current_result else None
        translation_form = TranslationForm()

        # Overall average confidence
        confidences = [r.confidence for r in results if r.confidence is not None]
        avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None

        # Total word count across all pages
        total_words = sum(r.word_count for r in results)
        total_chars = sum(r.char_count for r in results)

        latest_translation = TranslationResult.objects.filter(recognition_result=current_result).last()
        if not latest_translation:
            latest_translation = TranslationResult.objects.filter(recognition_result__document=doc).last()

        # Calibrated Confidence Categorization (High >= 75%, Medium 60-74%, Low < 60%)
        conf = current_result.confidence if (current_result and current_result.confidence is not None) else 0.0
        if conf >= 75.0:
            calibrated_level = 'High'
            calibrated_badge = 'success'
            calibrated_hint = 'High engine certainty across lines and characters.'
        elif conf >= 60.0:
            calibrated_level = 'Medium'
            calibrated_badge = 'warning'
            calibrated_hint = 'Moderate certainty: handwriting stroke or contrast variations detected.'
        else:
            calibrated_level = 'Low'
            calibrated_badge = 'danger'
            calibrated_hint = 'Low certainty: dense cursive strokes, non-uniform background, or faint ink.'

        # Quality & Error Evaluation (CER / WER)
        from django.conf import settings
        doc_evaluation = None
        ref_text = None
        is_tech_doc = '2nd' in doc.original_filename.lower() or '2nd' in doc.title.lower()
        gt_filename = 'ground_truth_handwritten_technical_notes.txt' if is_tech_doc else None
        if gt_filename:
            gt_path = os.path.join(settings.MEDIA_ROOT, 'samples', gt_filename)
            if os.path.exists(gt_path):
                try:
                    with open(gt_path, 'r', encoding='utf-8') as f:
                        ref_text = f.read().strip()
                except Exception:
                    pass

        if ref_text and current_result:
            current_metrics = compute_metrics(ref_text, current_result.effective_text)
            baseline_metrics = compute_metrics(ref_text, current_result.original_recognized_text) if current_result.original_recognized_text else None
            doc_evaluation = {
                'has_ground_truth': True,
                'ground_truth_name': gt_filename,
                'current_metrics': current_metrics,
                'baseline_metrics': baseline_metrics,
            }

        # Intermediate Preprocessing Images Inspection
        preproc_dir = os.path.join(settings.MEDIA_ROOT, 'preprocessed', str(doc.id))
        intermediate_steps = []
        steps_info = [
            ('step1_original.jpg', 'Step 1: Input Document', 'Original document image uploaded by user.'),
            ('step2_enhanced.jpg', 'Step 2: Illumination & Contrast', 'Morphological background division & CLAHE contrast boost.'),
            ('step3_ocr_input.jpg', 'Step 3: Preprocessed OCR Feed', 'Final preprocessed image supplied directly to EasyOCR/PyTorch.'),
        ]
        for fname, title, desc in steps_info:
            fpath = os.path.join(preproc_dir, fname)
            if os.path.exists(fpath):
                intermediate_steps.append({
                    'filename': fname,
                    'title': title,
                    'description': desc,
                    'url': f"{settings.MEDIA_URL}preprocessed/{doc.id}/{fname}",
                })

        # Benchmark reference comparison dataset
        benchmark_results = EvaluationService.evaluate_all()
        benchmark_summary = EvaluationService.get_summary_averages(benchmark_results)

        return render(request, 'documents/results.html', {
            'document': doc,
            'results': results,
            'current_result': current_result,
            'edit_form': edit_form,
            'translation_form': translation_form,
            'latest_translation': latest_translation,
            'avg_confidence': avg_confidence,
            'total_words': total_words,
            'total_chars': total_chars,
            'current_page': page_num,
            'calibrated_level': calibrated_level,
            'calibrated_badge': calibrated_badge,
            'calibrated_hint': calibrated_hint,
            'doc_evaluation': doc_evaluation,
            'intermediate_steps': intermediate_steps,
            'benchmark_results': benchmark_results,
            'benchmark_summary': benchmark_summary,
        })


class DocumentEditView(LoginRequiredMixin, View):
    """Saves user manual edits to recognition output with status tracking."""
    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        page_num = int(request.POST.get('page_number', 1))
        result = get_object_or_404(RecognitionResult, document=doc, page_number=page_num)

        form = DocumentEditForm(request.POST, instance=result)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.status_tracking = 'manually_edited'

            # Re-run structured extractor on edited text if medical or bank
            if doc.document_type == 'medical':
                obj.structured_data = MedicalPrescriptionExtractor.extract(
                    transcript=obj.effective_text,
                    confidence_details=obj.confidence_details
                )
            elif doc.document_type in ('bank', 'financial'):
                obj.structured_data = BankRecordExtractor.extract(
                    transcript=obj.effective_text,
                    confidence_details=obj.confidence_details
                )

            obj.save()
            messages.success(request, f"Changes saved for Page {page_num}!")
        else:
            messages.error(request, "Failed to save edits.")

        return redirect(f"{reverse('documents:results', kwargs={'pk': doc.pk})}?page={page_num}")


class DocumentTranslateView(LoginRequiredMixin, View):
    """Translates recognition text and displays side-by-side or returns JSON."""
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        results = doc.results.all().order_by('page_number')
        form = TranslationForm()
        latest_translation = TranslationResult.objects.filter(recognition_result__document=doc).last()

        return render(request, 'documents/translate.html', {
            'document': doc,
            'results': results,
            'form': form,
            'translation': latest_translation,
        })

    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        page_num = int(request.POST.get('page_number', 1))
        result = get_object_or_404(RecognitionResult, document=doc, page_number=page_num)

        target_lang = request.POST.get('target_language', '').strip()
        source_lang = request.POST.get('source_language', '').strip() or doc.selected_language
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('format') == 'json'

        if not target_lang:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Target language must be selected.'}, status=400)
            messages.error(request, 'Target language must be selected.')
            return redirect('documents:translate', pk=doc.pk)

        try:
            trans_record = TranslationService.translate_result(
                recognition_result=result,
                target_language=target_lang,
                source_language=source_lang
            )
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'target_language': trans_record.target_language.upper(),
                    'translated_text': trans_record.translated_text,
                    'provider': trans_record.provider,
                    'created_at': trans_record.created_at.strftime('%b %d, %H:%M'),
                    'id': trans_record.id
                }, json_dumps_params={'ensure_ascii': False})

            messages.success(request, f"Text translated successfully to {target_lang.upper()}!")
            return render(request, 'documents/translate.html', {
                'document': doc,
                'results': doc.results.all().order_by('page_number'),
                'form': TranslationForm(initial={'target_language': target_lang}),
                'translation': trans_record,
                'current_result': result,
            })
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
            messages.error(request, f"Translation error: {str(e)}")
            return redirect('documents:translate', pk=doc.pk)


class ExportTranslationTxtView(LoginRequiredMixin, View):
    """Exports latest translated text as UTF-8 TXT."""
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        latest_translation = TranslationResult.objects.filter(recognition_result__document=doc).last()
        if not latest_translation:
            messages.error(request, "No translation available to export. Please run translation first.")
            return redirect('documents:results', pk=doc.pk)
        stream = ExportService.export_translation_txt(latest_translation)
        response = HttpResponse(stream.getvalue(), content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{doc.title}_{latest_translation.target_language}_translation.txt"'
        return response


# Export Views
class ExportTxtView(LoginRequiredMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        stream = ExportService.export_txt(doc)
        response = HttpResponse(stream.getvalue(), content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{doc.title}_transcript.txt"'
        return response


class ExportCsvView(LoginRequiredMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        stream = ExportService.export_csv(doc)
        response = HttpResponse(stream.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{doc.title}_export.csv"'
        return response


class ExportDocxView(LoginRequiredMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        stream = ExportService.export_docx(doc)
        response = HttpResponse(
            stream.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{doc.title}_transcript.docx"'
        return response


class ExportPdfView(LoginRequiredMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        stream = ExportService.export_pdf(doc)
        response = HttpResponse(stream.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{doc.title}_report.pdf"'
        return response


class DocumentDeleteView(LoginRequiredMixin, View):
    """Deletes document with ownership validation and cascades filesystem cleanup."""
    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        title = doc.title
        doc.delete()
        messages.success(request, f"Document '{title}' and all associated OCR results were deleted.")
        return redirect('documents:list')
