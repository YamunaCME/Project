"""
Language and Engine Capability Registry.

Centralizes supported language metadata, script details, and OCR/HTR engine capabilities.
Enforces engine-language validation rules and prevents running unsupported combinations.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LanguageInfo:
    code: str
    name: str
    native_name: str
    script: str
    is_priority: bool = False


@dataclass(frozen=True)
class EngineCapability:
    engine_id: str
    display_name: str
    description: str
    is_local: bool
    requires_credentials: bool
    supports_printed: bool
    supports_handwritten: bool
    supports_confidence: bool
    supported_languages: Tuple[str, ...]
    handwriting_supported_languages: Tuple[str, ...]
    hardware_notes: str
    limitations: str


class LanguageRegistry:
    """Registry maintaining languages, scripts, and OCR engine capabilities."""

    LANGUAGES: Dict[str, LanguageInfo] = {
        'en': LanguageInfo('en', 'English', 'English', 'Latin', is_priority=True),
        'te': LanguageInfo('te', 'Telugu', 'తెలుగు', 'Telugu', is_priority=True),
        'hi': LanguageInfo('hi', 'Hindi', 'हिन्दी', 'Devanagari', is_priority=True),
        'ta': LanguageInfo('ta', 'Tamil', 'தமிழ்', 'Tamil', is_priority=False),
        'kn': LanguageInfo('kn', 'Kannada', 'ಕನ್ನಡ', 'Kannada', is_priority=False),
        'mr': LanguageInfo('mr', 'Marathi', 'मराठी', 'Devanagari', is_priority=False),
        'bn': LanguageInfo('bn', 'Bengali', 'বাংলা', 'Bengali', is_priority=False),
        'gu': LanguageInfo('gu', 'Gujarati', 'ગુજરાતી', 'Gujarati', is_priority=False),
        'pa': LanguageInfo('pa', 'Punjabi', 'ਪੰਜਾਬੀ', 'Gurmukhi', is_priority=False),
        'ur': LanguageInfo('ur', 'Urdu', 'اردو', 'Perso-Arabic', is_priority=False),
    }

    ENGINE_CAPABILITIES: Dict[str, EngineCapability] = {
        'easyocr': EngineCapability(
            engine_id='easyocr',
            display_name='EasyOCR (Deep Learning)',
            description='Local deep-learning OCR utilizing PyTorch and CRAFT text detection. Free, runs offline.',
            is_local=True,
            requires_credentials=False,
            supports_printed=True,
            supports_handwritten=True,
            supports_confidence=True,
            supported_languages=('en', 'hi', 'te', 'ta', 'kn', 'mr', 'bn', 'gu', 'pa', 'ur'),
            handwriting_supported_languages=('en', 'hi', 'te', 'ta', 'kn', 'mr', 'bn'),
            hardware_notes='Runs on CPU or NVIDIA CUDA GPU. Initial run downloads model weights (~100MB per script).',
            limitations='Handwriting accuracy depends on legibility; cursive or heavily overlapping strokes may have lower confidence.',
        ),
        'trocr': EngineCapability(
            engine_id='trocr',
            display_name='TrOCR (Transformer OCR)',
            description='Transformer-based encoder-decoder model specialized in English handwriting recognition.',
            is_local=True,
            requires_credentials=False,
            supports_printed=True,
            supports_handwritten=True,
            supports_confidence=True,
            supported_languages=('en',),
            handwriting_supported_languages=('en',),
            hardware_notes='PyTorch CPU or CUDA GPU. Requires ~1.5GB RAM for trocr-small.',
            limitations='Supports English only. Pretrained models from Microsoft are not trained on Indian scripts (Telugu, Hindi, etc.).',
        ),
        'google_vision': EngineCapability(
            engine_id='google_vision',
            display_name='Google Cloud Vision',
            description='Cloud document text detection engine supporting multi-script printed and handwritten recognition.',
            is_local=False,
            requires_credentials=True,
            supports_printed=True,
            supports_handwritten=True,
            supports_confidence=True,
            supported_languages=('en', 'hi', 'te', 'ta', 'kn', 'mr', 'bn', 'gu', 'pa', 'ur'),
            handwriting_supported_languages=('en', 'hi', 'te', 'ta', 'kn', 'mr', 'bn', 'gu', 'pa', 'ur'),
            hardware_notes='Cloud execution. Minimal local CPU/memory footprint.',
            limitations='Requires active Google Cloud credentials and internet connection. Subject to GCP API billing and quotas.',
        ),
    }

    @classmethod
    def get_all_languages(cls) -> List[Dict]:
        """Returns list of all registered languages formatted for templates."""
        return [
            {
                'code': lang.code,
                'name': lang.name,
                'native_name': lang.native_name,
                'script': lang.script,
                'is_priority': lang.is_priority,
            }
            for lang in cls.LANGUAGES.values()
        ]

    @classmethod
    def get_language(cls, code: str) -> Optional[LanguageInfo]:
        """Fetches language info by ISO code."""
        return cls.LANGUAGES.get(code.lower().strip())

    @classmethod
    def get_available_engines(cls) -> List[Dict]:
        """Returns metadata for all configured OCR engines."""
        return [
            {
                'id': cap.engine_id,
                'name': cap.display_name,
                'description': cap.description,
                'is_local': cap.is_local,
                'requires_credentials': cap.requires_credentials,
                'supports_printed': cap.supports_printed,
                'supports_handwritten': cap.supports_handwritten,
                'supports_confidence': cap.supports_confidence,
                'supported_languages': list(cap.supported_languages),
                'handwriting_supported_languages': list(cap.handwriting_supported_languages),
                'hardware_notes': cap.hardware_notes,
                'limitations': cap.limitations,
            }
            for cap in cls.ENGINE_CAPABILITIES.values()
        ]

    @classmethod
    def is_engine_compatible(
        cls,
        engine_id: str,
        language_code: str,
        document_type: str = 'printed',
    ) -> Tuple[bool, str]:
        """
        Validates if an engine can process the given language and document type.
        Returns (is_compatible: bool, reason_message: str).
        """
        engine_id = engine_id.lower().strip()
        lang_code = language_code.lower().strip()
        doc_type = document_type.lower().strip()

        cap = cls.ENGINE_CAPABILITIES.get(engine_id)
        if not cap:
            return False, f"Unknown OCR engine '{engine_id}'."

        lang = cls.get_language(lang_code)
        if not lang:
            return False, f"Unsupported language code '{lang_code}'."

        # Check language support
        if lang_code not in cap.supported_languages:
            return (
                False,
                f"Engine '{cap.display_name}' does not support {lang.name} ({lang.script} script). "
                f"Supported languages: {', '.join(cap.supported_languages)}."
            )

        # Check handwriting support
        is_handwriting = doc_type in ('handwritten', 'medical', 'academic', 'mixed')
        if is_handwriting and lang_code not in cap.handwriting_supported_languages:
            return (
                False,
                f"Engine '{cap.display_name}' does not support handwritten {lang.name}. "
                f"TrOCR is English-only. Please use EasyOCR or Google Cloud Vision."
            )

        return True, "Compatible"

    @classmethod
    def get_compatible_engines(cls, language_code: str, document_type: str = 'printed') -> List[Dict]:
        """Finds all engines compatible with a given language and document type."""
        compatible = []
        for engine_id in cls.ENGINE_CAPABILITIES.keys():
            is_valid, _ = cls.is_engine_compatible(engine_id, language_code, document_type)
            if is_valid:
                compatible.append(cls.ENGINE_CAPABILITIES[engine_id])
        return [
            {
                'id': cap.engine_id,
                'name': cap.display_name,
                'is_local': cap.is_local,
                'requires_credentials': cap.requires_credentials,
            }
            for cap in compatible
        ]
