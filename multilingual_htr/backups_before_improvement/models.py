import os
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


class Document(models.Model):
    """Uploaded document representation supporting images and PDFs."""

    STATUS_CHOICES = [
        ('pending', 'Pending Recognition'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('handwritten', 'General Handwritten Notes'),
        ('printed', 'Printed Document'),
        ('academic', 'Academic Notes & Textbooks'),
        ('medical', 'Medical Prescription & Clinical Document'),
        ('bank', 'Bank Statement & Banking Record'),
        ('financial', 'Invoice / Receipt / Financial Form'),
        ('mixed', 'Mixed / Auto Detect'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    original_file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    processed_file = models.ImageField(upload_to='preprocessed/%Y/%m/%d/', blank=True, null=True)
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    detected_language = models.CharField(max_length=16, blank=True, null=True)
    selected_language = models.CharField(max_length=16, default='en')
    document_type = models.CharField(max_length=32, choices=DOCUMENT_TYPE_CHOICES, default='printed')
    page_count = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
    file_size = models.PositiveBigIntegerField(default=0)  # in bytes

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()}) - {self.user.username}"

    def get_absolute_url(self):
        return reverse('documents:detail', kwargs={'pk': self.pk})

    @property
    def is_pdf(self) -> bool:
        return self.original_filename.lower().endswith('.pdf')

    @property
    def formatted_file_size(self) -> str:
        """Human-readable file size."""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def delete(self, *args, **kwargs):
        """Clean up filesystem assets when document record is deleted."""
        for field in [self.original_file, self.processed_file]:
            if field and hasattr(field, 'path') and os.path.exists(field.path):
                try:
                    os.remove(field.path)
                except OSError:
                    pass
        super().delete(*args, **kwargs)


class RecognitionResult(models.Model):
    """Stores OCR/HTR transcription output per document page."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='results')
    page_number = models.PositiveIntegerField(default=1)
    original_recognized_text = models.TextField()
    edited_text = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)  # 0.0 to 100.0 scale percentage
    processing_duration = models.FloatField(default=0.0)  # in seconds
    provider_name = models.CharField(max_length=50)  # 'easyocr', 'trocr', 'google_vision'
    confidence_details = models.JSONField(default=list, blank=True)
    structured_data = models.JSONField(default=dict, blank=True)
    status_tracking = models.CharField(max_length=32, default='raw')  # 'raw', 'machine_corrected', 'manually_edited'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page_number']
        unique_together = ('document', 'page_number')

    def __str__(self):
        return f"Result: {self.document.title} - Page {self.page_number} ({self.provider_name})"

    @property
    def effective_text(self) -> str:
        """Returns edited text if modified by user, otherwise original output."""
        return self.edited_text if self.edited_text.strip() else self.original_recognized_text

    @property
    def word_count(self) -> int:
        return len(self.effective_text.split())

    @property
    def char_count(self) -> int:
        return len(self.effective_text)


class RecognitionJob(models.Model):
    """Audit and tracking record for asynchronous or synchronous recognition runs."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='queued')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    safe_error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Job #{self.id} for {self.document.title} [{self.status}]"


class TranslationResult(models.Model):
    """Optional translation record linked to recognized document results."""

    recognition_result = models.ForeignKey(RecognitionResult, on_delete=models.CASCADE, related_name='translations')
    source_language = models.CharField(max_length=16)
    target_language = models.CharField(max_length=16)
    translated_text = models.TextField()
    provider = models.CharField(max_length=50, default='deep-translator')
    status = models.CharField(max_length=32, default='completed')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Translation ({self.source_language} -> {self.target_language}) for {self.recognition_result.document.title}"
