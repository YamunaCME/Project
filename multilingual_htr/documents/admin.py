from django.contrib import admin
from .models import Document, RecognitionResult, RecognitionJob, TranslationResult


class RecognitionResultInline(admin.TabularInline):
    model = RecognitionResult
    extra = 0
    fields = ('page_number', 'provider_name', 'confidence', 'processing_duration', 'created_at')
    readonly_fields = ('created_at',)


class RecognitionJobInline(admin.TabularInline):
    model = RecognitionJob
    extra = 0
    fields = ('status', 'started_at', 'completed_at', 'safe_error_code', 'retry_count')
    readonly_fields = ('started_at', 'completed_at')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'selected_language', 'document_type', 'status', 'page_count', 'formatted_file_size', 'uploaded_at')
    list_filter = ('status', 'document_type', 'selected_language', 'uploaded_at')
    search_fields = ('title', 'original_filename', 'user__username', 'user__email')
    readonly_fields = ('uploaded_at', 'file_size', 'formatted_file_size')
    inlines = [RecognitionResultInline, RecognitionJobInline]


@admin.register(RecognitionResult)
class RecognitionResultAdmin(admin.ModelAdmin):
    list_display = ('document', 'page_number', 'provider_name', 'confidence', 'word_count', 'processing_duration', 'created_at')
    list_filter = ('provider_name', 'created_at')
    search_fields = ('document__title', 'original_recognized_text', 'edited_text')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RecognitionJob)
class RecognitionJobAdmin(admin.ModelAdmin):
    list_display = ('document', 'status', 'started_at', 'completed_at', 'safe_error_code', 'retry_count')
    list_filter = ('status', 'started_at')
    search_fields = ('document__title', 'safe_error_code', 'safe_error_message')


@admin.register(TranslationResult)
class TranslationResultAdmin(admin.ModelAdmin):
    list_display = ('recognition_result', 'source_language', 'target_language', 'provider', 'created_at')
    list_filter = ('source_language', 'target_language', 'provider')
    search_fields = ('translated_text', 'recognition_result__document__title')
