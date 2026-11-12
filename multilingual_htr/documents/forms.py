import os
from django import forms
from django.conf import settings
from PIL import Image
import io

from .models import Document, RecognitionResult
from .services.language_registry import LanguageRegistry


class DocumentUploadForm(forms.ModelForm):
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.pdf'}

    selected_language = forms.ChoiceField(
        choices=(),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'languageSelect'
        }),
        label="Language Script"
    )

    class Meta:
        model = Document
        fields = ['title', 'original_file', 'selected_language', 'document_type']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Document title (leave blank to use filename)'
            }),
            'original_file': forms.FileInput(attrs={
                'class': 'form-control',
                'id': 'fileUploadInput',
                'accept': '.jpg,.jpeg,.png,.tif,.tiff,.pdf'
            }),
            'document_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'documentTypeSelect'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate language choices dynamically from registry
        languages = LanguageRegistry.get_all_languages()
        self.fields['selected_language'].choices = [
            (lang['code'], f"{lang['name']} ({lang['native_name']}) - {lang['script']} script")
            for lang in languages
        ]
        self.fields['selected_language'].initial = 'en'
        self.fields['title'].required = False

    def clean_original_file(self):
        uploaded_file = self.cleaned_data.get('original_file')
        if not uploaded_file:
            raise forms.ValidationError("Please select a file to upload.")

        # 1. Check file size and empty uploads
        if uploaded_file.size == 0:
            raise forms.ValidationError("The uploaded file is empty (0 bytes).")

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_bytes:
            raise forms.ValidationError(
                f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        # 2. Check extension
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                f"Unsupported file format '{ext}'. Allowed formats: JPG, JPEG, PNG, TIFF, PDF."
            )

        # 3. Server-side file content signature verification
        uploaded_file.seek(0)
        file_header = uploaded_file.read(1024)
        uploaded_file.seek(0)

        if ext == '.pdf':
            if not file_header.startswith(b'%PDF-'):
                raise forms.ValidationError("Invalid PDF file structure or corrupted document.")
        else:
            try:
                # Stream validation directly on uploaded_file without unnecessary buffering in memory
                uploaded_file.seek(0)
                with Image.open(uploaded_file) as img:
                    img_format = (img.format or '').upper()
                    allowed_formats = {'JPEG', 'PNG', 'TIFF', 'MPO'}
                    if img_format not in allowed_formats:
                        raise forms.ValidationError(
                            f"Image format '{img_format}' is not supported. Please upload a JPEG, PNG, or TIFF image."
                        )
                    img.verify()
            except forms.ValidationError:
                raise
            except Exception:
                raise forms.ValidationError("The uploaded file is not a valid or readable image.")
            finally:
                uploaded_file.seek(0)

        return uploaded_file

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get('original_file')
        title = cleaned_data.get('title')
        if file and not title:
            # Default title to file name without extension
            base_name = os.path.splitext(file.name)[0].replace('_', ' ').replace('-', ' ').title()
            cleaned_data['title'] = base_name
        return cleaned_data


class RecognitionConfigForm(forms.Form):
    """Configuration form for triggering OCR/HTR processing."""
    engine = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'engineSelect'}),
        label="OCR Engine"
    )
    document_type = forms.ChoiceField(
        choices=Document.DOCUMENT_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'documentTypeConfigSelect'}),
        label="Document Form / Category"
    )
    apply_deskew = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'deskewCheck'}),
        label="Deskew & Rotate Orientation"
    )
    apply_illumination = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'illuminationCheck'}),
        label="Shadow Removal & Illumination Flattening"
    )
    apply_clahe = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'claheCheck'}),
        label="Contrast Enhancement (CLAHE)"
    )
    apply_sharpening = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'sharpeningCheck'}),
        label="Ink Stroke Sharpening"
    )
    apply_denoising = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'denoiseCheck'}),
        label="Noise Filtering (Denoising)"
    )
    apply_threshold = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'thresholdCheck'}),
        label="Binarization / Adaptive Thresholding"
    )

    def __init__(self, *args, **kwargs):
        document = kwargs.pop('document', None)
        self.document = document
        super().__init__(*args, **kwargs)
        engines = LanguageRegistry.get_available_engines()
        self.fields['engine'].choices = [
            (eng['id'], f"{eng['name']} ({'Offline Local' if eng['is_local'] else 'Cloud'})")
            for eng in engines
        ]
        if document:
            # Set default based on user profile or engine preference
            self.fields['engine'].initial = settings.DEFAULT_OCR_ENGINE
            self.fields['document_type'].initial = document.document_type

    def clean(self):
        cleaned_data = super().clean()
        engine = cleaned_data.get('engine')
        doc_type = cleaned_data.get('document_type') or (self.document.document_type if hasattr(self, 'document') and self.document else 'printed')
        cleaned_data['document_type'] = doc_type
        if engine and hasattr(self, 'document') and self.document:
            is_compat, reason = LanguageRegistry.is_engine_compatible(
                engine_id=engine,
                language_code=self.document.selected_language,
                document_type=doc_type
            )
            if not is_compat:
                self.add_error('engine', reason)
        return cleaned_data


class DocumentEditForm(forms.ModelForm):
    """Form to edit and correct transcription text."""
    class Meta:
        model = RecognitionResult
        fields = ['edited_text']
        widgets = {
            'edited_text': forms.Textarea(attrs={
                'class': 'form-control ocr-editor-textarea',
                'rows': 16,
                'placeholder': 'Edit or correct OCR transcribed text here...'
            }),
        }


class TranslationForm(forms.Form):
    """Form for translation configuration."""
    target_language = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Translate Into"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        languages = LanguageRegistry.get_all_languages()
        self.fields['target_language'].choices = [
            (lang['code'], f"{lang['name']} ({lang['native_name']})")
            for lang in languages
        ]
