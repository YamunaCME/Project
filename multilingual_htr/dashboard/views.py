import json
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Avg

from documents.models import Document, RecognitionResult, RecognitionJob
from documents.services.language_registry import LanguageRegistry


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        user_docs = Document.objects.filter(user=user)

        total_documents = user_docs.count()
        completed_count = user_docs.filter(status='completed').count()
        failed_count = user_docs.filter(status='failed').count()
        pending_count = user_docs.filter(status__in=['pending', 'processing']).count()

        recent_documents = user_docs.order_by('-uploaded_at')[:6]
        recent_results = RecognitionResult.objects.filter(
            document__user=user
        ).select_related('document').order_by('-created_at')[:5]

        # Calculate average recognition confidence
        avg_conf_data = RecognitionResult.objects.filter(
            document__user=user,
            confidence__isnull=False
        ).aggregate(Avg('confidence'))
        avg_confidence = round(avg_conf_data['confidence__avg'], 1) if avg_conf_data['confidence__avg'] else 0.0

        # Distribution by Document Type
        type_qs = user_docs.values('document_type').annotate(count=Count('id'))
        type_data = {'printed': 0, 'handwritten': 0, 'mixed': 0}
        for item in type_qs:
            type_data[item['document_type']] = item['count']

        # Distribution by Language
        lang_qs = user_docs.values('selected_language').annotate(count=Count('id'))
        lang_labels = []
        lang_counts = []
        for item in lang_qs:
            code = item['selected_language']
            lang_obj = LanguageRegistry.get_language(code)
            label = lang_obj.name if lang_obj else code.upper()
            lang_labels.append(label)
            lang_counts.append(item['count'])

        context = {
            'total_documents': total_documents,
            'completed_count': completed_count,
            'failed_count': failed_count,
            'pending_count': pending_count,
            'avg_confidence': avg_confidence,
            'recent_documents': recent_documents,
            'recent_results': recent_results,
            'chart_type_labels': json.dumps(['Printed', 'Handwritten', 'Mixed']),
            'chart_type_data': json.dumps([type_data['printed'], type_data['handwritten'], type_data['mixed']]),
            'chart_lang_labels': json.dumps(lang_labels),
            'chart_lang_data': json.dumps(lang_counts),
        }
        return render(request, 'dashboard/index.html', context)
