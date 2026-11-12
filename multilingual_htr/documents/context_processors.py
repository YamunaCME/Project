from django.conf import settings
from documents.services.language_registry import LanguageRegistry

def system_info(request):
    """Provides global system context for templates."""
    return {
        'APP_NAME': 'Multilingual HTR',
        'DEFAULT_OCR_ENGINE': settings.DEFAULT_OCR_ENGINE,
        'MAX_UPLOAD_SIZE_MB': settings.MAX_UPLOAD_SIZE_MB,
        'SUPPORTED_LANGUAGES': LanguageRegistry.get_all_languages(),
        'ACTIVE_ENGINES': LanguageRegistry.get_available_engines(),
    }
