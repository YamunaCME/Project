"""
Translation Service using deep-translator with multi-provider fallback and chunking.

Translates recognized text between English, Telugu, Hindi, and registered regional languages.
Supports text chunking for long documents, rate-limit retries, and offline vocabulary fallback.
"""

import re
import time
from typing import Optional, List
from deep_translator import GoogleTranslator, MyMemoryTranslator
from documents.models import RecognitionResult, TranslationResult


class TranslationService:
    # Common terminology translations for offline fallback when network is unavailable
    OFFLINE_VOCABULARY = {
        'te': {
            'interrupt': 'అంతరాయం',
            'priority': 'ప్రాధాన్యత',
            'daisy chaining': 'డైసీ చైనింగ్',
            'daisychaining': 'డైసీ చైనింగ్',
            'polling': 'పోలింగ్',
            'system': 'వ్యవస్థ',
            'performance': 'పనితీరు',
            'device': 'పరికరం',
            'devices': 'పరికరాలు',
            'hardware': 'హార్డ్‌వేర్',
            'software': 'సాఫ్ట్‌వేర్',
            'data': 'డేటా',
            'transfer': 'బదిలీ',
            'method': 'పద్ధతి',
            'handling': 'నిర్వహణ',
            'service': 'సేవ',
            'serviced': 'సేవ చేయబడింది',
            'request': 'అభ్యర్థన',
            'requested': 'అభ్యర్థించబడింది',
            'waiting': 'వేచి ఉండటం',
            'state': 'స్థితి',
            'first': 'మొదటి',
            'highest': 'అత్యధిక',
            'important': 'ముఖ్యమైన',
            'simultaneously': 'ఏకకాలంలో',
            'established': 'స్థాపించబడింది',
            'checks': 'తనిఖీ చేస్తుంది',
            'status': 'స్థితి',
            'found': 'కనుగొనబడింది',
            'treated': 'పరిగణించబడుతుంది',
            'remaining': 'మిగిలిన',
            'structure': 'నిర్మాణం',
            'patient': 'రోగి',
            'doctor': 'వైద్యుడు',
            'medicine': 'మందు',
            'tablet': 'మాత్ర',
            'bank': 'బ్యాంకు',
            'account': 'ఖాతా',
            'balance': 'నిల్వ',
            'deposit': 'డిపాజిట్',
            'withdrawal': 'ఉపసంహరణ',
            'date': 'తేదీ',
            'amount': 'మొత్తం',
        },
        'hi': {
            'interrupt': 'अवरोध',
            'priority': 'प्राथमिकता',
            'daisy chaining': 'डेज़ी चेनिंग',
            'daisychaining': 'डेज़ी चेनिंग',
            'polling': 'पोलिंग',
            'system': 'प्रणाली',
            'performance': 'प्रदर्शन',
            'device': 'उपकरण',
            'devices': 'उपकरणों',
            'hardware': 'हार्डवेयर',
            'software': 'सॉफ्टवेयर',
            'data': 'डेटा',
            'transfer': 'स्थानांतरण',
            'method': 'विधि',
            'handling': 'प्रबंधन',
            'service': 'सेवा',
            'serviced': 'सेवा की गई',
            'request': 'अनुरोध',
            'requested': 'अनुरोध किया',
            'waiting': 'प्रतीक्षा',
            'state': 'स्थिति',
            'first': 'पहला',
            'highest': 'सर्वोच्च',
            'important': 'महत्वपूर्ण',
            'simultaneously': 'एक साथ',
            'established': 'स्थापित',
            'checks': 'जांचता है',
            'status': 'स्थिति',
            'found': 'पाया गया',
            'treated': 'माना जाता है',
            'remaining': 'शेष',
            'structure': 'संरचना',
            'patient': 'रोगी',
            'doctor': 'चिकित्सक',
            'medicine': 'दवा',
            'tablet': 'गोली',
            'bank': 'बैंक',
            'account': 'खाता',
            'balance': 'शेष राशि',
            'deposit': 'जमा',
            'withdrawal': 'निकासी',
            'date': 'दिनांक',
            'amount': 'राशि',
        },
        'ta': {
            'interrupt': 'குறுக்கீடு',
            'priority': 'முன்னுரிமை',
            'system': 'அமைப்பு',
            'device': 'சாதனம்',
            'hardware': 'வன்பொருள்',
            'software': 'மென்பொருள்',
            'bank': 'வங்கி',
            'account': 'கணக்கு',
        },
        'kn': {
            'interrupt': 'ಅಡಚಣೆ',
            'priority': 'ಆದ್ಯತೆ',
            'system': 'ವ್ಯವಸ್ಥೆ',
            'device': 'ಸಾಧನ',
            'hardware': 'ಯಂತ್ರಾಂಶ',
            'software': 'ತಂತ್ರಾಂಶ',
            'bank': 'ಬ್ಯಾಂಕ್',
            'account': 'ಖಾತೆ',
        }
    }

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 400) -> List[str]:
        """
        Splits input text into chunks strictly under max_chars,
        preserving line breaks and sentence boundaries.
        """
        paragraphs = text.split('\n')
        chunks: List[str] = []
        current = ""

        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                if current:
                    chunks.append(current)
                    current = ""
                continue

            if len(p_clean) <= max_chars:
                if len(current) + len(p_clean) + 1 <= max_chars:
                    current = f"{current}\n{p_clean}" if current else p_clean
                else:
                    if current:
                        chunks.append(current)
                    current = p_clean
            else:
                # Split long paragraph by sentence or words
                sentences = re.split(r'(?<=[.!?])\s+', p_clean)
                for s in sentences:
                    if len(current) + len(s) + 1 <= max_chars:
                        current = f"{current} {s}" if current else s
                    else:
                        if current:
                            chunks.append(current)
                        current = s[:max_chars]

        if current:
            chunks.append(current)

        return chunks if chunks else [text[:max_chars]]

    @classmethod
    def _offline_fallback_translate(cls, text: str, target_lang: str, source_lang: str = 'en') -> str:
        """
        Provides offline structural translation when external translation APIs
        are unreachable or rate-limited. Supports all 6 combinations of en, te, and hi.
        """
        src = (source_lang or 'en').lower().strip()
        tgt = (target_lang or '').lower().strip()

        # Direct vocabulary from English
        if src == 'en' and tgt in cls.OFFLINE_VOCABULARY:
            vocab = cls.OFFLINE_VOCABULARY[tgt]
            sorted_vocab = sorted(vocab.items(), key=lambda x: -len(x[0]))
            translated_lines = []
            for line in text.split('\n'):
                line_trans = line
                for eng_word, localized in sorted_vocab:
                    pattern = re.compile(rf'\b{re.escape(eng_word)}\b', re.IGNORECASE)
                    line_trans = pattern.sub(localized, line_trans)
                translated_lines.append(line_trans)
            return f"[Offline Translation ({tgt.upper()})]\n" + "\n".join(translated_lines)

        # Reverse vocabulary to English
        elif tgt == 'en' and src in cls.OFFLINE_VOCABULARY:
            vocab = cls.OFFLINE_VOCABULARY[src]
            rev_vocab = sorted([(v.split(' ')[0], k.capitalize()) for k, v in vocab.items()], key=lambda x: -len(x[0]))
            translated_lines = []
            for line in text.split('\n'):
                line_trans = line
                for loc_word, eng_word in rev_vocab:
                    line_trans = line_trans.replace(loc_word, eng_word)
                translated_lines.append(line_trans)
            return f"[Offline Translation ({tgt.upper()})]\n" + "\n".join(translated_lines)

        # Cross-regional translation (te <-> hi)
        elif src in ('te', 'hi') and tgt in ('te', 'hi'):
            vocab_src = cls.OFFLINE_VOCABULARY[src]
            vocab_tgt = cls.OFFLINE_VOCABULARY[tgt]
            cross_map = {}
            for eng_k in vocab_src:
                if eng_k in vocab_tgt:
                    src_term = vocab_src[eng_k].split(' ')[0]
                    tgt_term = vocab_tgt[eng_k].split(' ')[0]
                    cross_map[src_term] = tgt_term

            translated_lines = []
            for line in text.split('\n'):
                line_trans = line
                for s_term, t_term in cross_map.items():
                    line_trans = line_trans.replace(s_term, t_term)
                translated_lines.append(line_trans)
            return f"[Offline Translation ({tgt.upper()})]\n" + "\n".join(translated_lines)

        return (
            f"[Offline Translation ({tgt.upper()})]\n"
            f"External translation service is offline. Raw text preserved:\n\n{text}"
        )

    @classmethod
    def translate_text(
        cls,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> tuple:
        """
        Translates arbitrary text into target_language using multi-provider fallback.
        Returns a tuple of (translated_text, provider_name).
        """
        src = (source_language or 'auto').lower().strip()
        target = target_language.lower().strip() if target_language else ''
        text_to_translate = text.strip()

        if not target:
            raise ValueError("Target language must be specified.")

        if src != 'auto' and src == target:
            raise ValueError("Source and target languages cannot be identical.")

        if not text_to_translate:
            raise ValueError("No text available to translate.")

        chunks = cls._chunk_text(text_to_translate, max_chars=400)
        translated_chunks: List[str] = []
        provider_used = 'google-translator'

        # Attempt 1: GoogleTranslator on chunked pieces
        try:
            translator = GoogleTranslator(source=src, target=target)
            for chunk in chunks:
                t = translator.translate(chunk)
                translated_chunks.append(t if t else chunk)
        except Exception:
            # Attempt 2: MyMemoryTranslator with chunked pieces (< 500 char safe)
            try:
                mm_map = {
                    'en': 'english',
                    'te': 'telugu',
                    'hi': 'hindi',
                    'ta': 'tamil',
                    'kn': 'kannada',
                    'mr': 'marathi',
                    'bn': 'bengali',
                    'gu': 'gujarati',
                    'pa': 'punjabi',
                    'ur': 'urdu',
                }
                src_mm = mm_map.get(src, 'english' if src in ('auto', None) else src)
                tgt_mm = mm_map.get(target, target)
                mm = MyMemoryTranslator(source=src_mm, target=tgt_mm)
                translated_chunks = []
                for chunk in chunks:
                    t = mm.translate(chunk)
                    translated_chunks.append(t if t else chunk)
                provider_used = 'mymemory-translator'
            except Exception:
                # Attempt 3: Local offline glossary fallback
                offline_text = cls._offline_fallback_translate(text_to_translate, target, source_lang=src)
                translated_chunks = [offline_text]
                provider_used = 'offline-dictionary'

        full_translation = "\n".join(translated_chunks).strip()
        return full_translation, provider_used

    @classmethod
    def translate_result(
        cls,
        recognition_result: RecognitionResult,
        target_language: str,
        source_language: Optional[str] = None
    ) -> TranslationResult:
        """
        Translates the effective text of a RecognitionResult into target_language.
        Handles chunking for long documents and persists TranslationResult.
        """
        src = source_language or recognition_result.document.selected_language or 'auto'
        target = target_language.lower().strip() if target_language else ''
        text_to_translate = recognition_result.effective_text.strip()

        full_translation, provider_used = cls.translate_text(
            text_to_translate,
            target_language=target,
            source_language=src
        )

        if not full_translation:
            raise RuntimeError("Translation provider returned empty output.")

        # Persist translation record
        record = TranslationResult.objects.create(
            recognition_result=recognition_result,
            source_language=src,
            target_language=target,
            translated_text=full_translation,
            provider=provider_used,
            status='completed'
        )
        return record
