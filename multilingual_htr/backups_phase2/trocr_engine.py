"""
TrOCR (Transformer OCR) Engine Implementation.

Employs Hugging Face Transformers vision encoder-decoder models
specialized for English handwriting text recognition.
Enforces script and language guards against unsupported Indian scripts.
"""

import time
import os
import cv2
import numpy as np
from PIL import Image
import torch
from django.conf import settings
from .language_registry import LanguageRegistry


class TrOCREngine:
    """Singleton-cached TrOCR engine using Hugging Face Transformers."""

    _processor = None
    _model = None
    _model_id = None
    _device = None

    @classmethod
    def _get_device(cls) -> torch.device:
        if cls._device is None:
            cls._device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        return cls._device

    @classmethod
    def load_model(cls):
        """Loads processor and model lazily into memory once."""
        model_id = getattr(settings, 'TROCR_MODEL_ID', 'microsoft/trocr-small-handwritten')
        if cls._model is None or cls._model_id != model_id:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            try:
                cls._processor = TrOCRProcessor.from_pretrained(model_id, local_files_only=True)
                cls._model = VisionEncoderDecoderModel.from_pretrained(model_id, local_files_only=True)
            except Exception:
                cls._processor = TrOCRProcessor.from_pretrained(model_id)
                cls._model = VisionEncoderDecoderModel.from_pretrained(model_id)
            cls._model.to(cls._get_device())
            cls._model.eval()
            cls._model_id = model_id
        return cls._processor, cls._model

    @staticmethod
    def _segment_text_lines(image_bgr: np.ndarray) -> list[Image.Image]:
        """
        Segments whole document image into text line crops using horizontal projection.
        Falls back to returning whole image if segmentation yields no lines.
        """
        if image_bgr is None or image_bgr.size == 0 or image_bgr.shape[0] == 0 or image_bgr.shape[1] == 0:
            return []

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        # Binarize inverted
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Horizontal projection
        proj = np.sum(thresh, axis=1)
        h, w = gray.shape

        lines = []
        in_line = False
        start_y = 0

        for y in range(h):
            has_pixels = proj[y] > (w * 0.01 * 255)  # threshold
            if has_pixels and not in_line:
                in_line = True
                start_y = max(0, y - 4)
            elif not has_pixels and in_line:
                in_line = False
                end_y = min(h, y + 4)
                if (end_y - start_y) > 12:  # minimum line height
                    crop = image_bgr[start_y:end_y, :]
                    if crop.size > 0:
                        rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                        lines.append(Image.fromarray(rgb_crop))

        # Handle line continuing to bottom of image (BUG 2 fix)
        if in_line:
            end_y = h
            if (end_y - start_y) > 12:
                crop = image_bgr[start_y:end_y, :]
                if crop.size > 0:
                    rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    lines.append(Image.fromarray(rgb_crop))

        if not lines:
            # Fallback to entire image
            rgb_full = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            lines.append(Image.fromarray(rgb_full))

        return lines

    @classmethod
    def recognize(
        cls,
        image_input,
        language_code: str = 'en',
        document_type: str = 'handwritten',
        **kwargs
    ) -> dict:
        """
        Performs handwriting recognition using TrOCR.
        Guards against non-English scripts.
        """
        lang = language_code.lower().strip()
        if lang != 'en':
            raise ValueError(
                f"TrOCR currently only supports English (Latin script) handwriting. "
                f"For {lang.upper()} documents, please select EasyOCR or Google Cloud Vision."
            )

        start_time = time.time()
        processor, model = cls.load_model()
        device = cls._get_device()

        # Load image into numpy BGR
        if isinstance(image_input, str):
            image_bgr = cv2.imread(image_input)
            if image_bgr is None:
                with Image.open(image_input) as pil_img:
                    image_bgr = cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)
        elif isinstance(image_input, Image.Image):
            image_bgr = cv2.cvtColor(np.array(image_input.convert('RGB')), cv2.COLOR_RGB2BGR)
        elif isinstance(image_input, np.ndarray):
            image_bgr = image_input
        else:
            raise ValueError("Unsupported image format for TrOCR.")

        if image_bgr is None or image_bgr.size == 0 or image_bgr.shape[0] == 0 or image_bgr.shape[1] == 0:
            return {
                'text': '',
                'confidence': 0.0,
                'duration': round(time.time() - start_time, 3),
                'line_count': 0,
                'provider': 'trocr',
            }

        # Segment image into lines for optimal transformer attention
        line_crops = cls._segment_text_lines(image_bgr)
        recognized_lines = []
        confidences = []

        with torch.no_grad():
            for line_img in line_crops:
                pixel_values = processor(line_img, return_tensors="pt").pixel_values.to(device)
                outputs = model.generate(
                    pixel_values,
                    return_dict_in_generate=True,
                    output_scores=True,
                    max_new_tokens=64
                )
                pred_ids = outputs.sequences
                line_text = processor.batch_decode(pred_ids, skip_special_tokens=True)[0].strip()

                if line_text:
                    recognized_lines.append(line_text)

                    # Calculate confidence from probabilities of actual predicted tokens (BUG 7 fix)
                    if hasattr(outputs, 'scores') and outputs.scores:
                        token_probs = []
                        tokenizer = getattr(processor, 'tokenizer', None)
                        special_ids = set(tokenizer.all_special_ids) if tokenizer and hasattr(tokenizer, 'all_special_ids') else set()

                        for i, step_score in enumerate(outputs.scores):
                            if i + 1 < pred_ids.shape[1]:
                                token_id = pred_ids[0, i + 1].item()
                                if token_id not in special_ids:
                                    step_probs = torch.softmax(step_score[0], dim=-1)
                                    token_probs.append(step_probs[token_id].item())

                        if token_probs:
                            confidences.append(sum(token_probs) / len(token_probs))
                        else:
                            # Fallback: compute average softmax from scores directly
                            step_maxes = [torch.softmax(s[0], dim=-1).max().item() for s in outputs.scores]
                            if step_maxes:
                                confidences.append(sum(step_maxes) / len(step_maxes))

        duration = time.time() - start_time
        full_text = "\n".join(recognized_lines)

        avg_confidence = round((sum(confidences) / len(confidences) * 100.0), 2) if confidences else 0.0

        confidence_details = []
        for idx, line_text in enumerate(recognized_lines):
            line_conf = round(confidences[idx] * 100.0, 1) if idx < len(confidences) else avg_confidence
            words_data = [
                {
                    'word': w,
                    'confidence': line_conf,
                    'is_low_confidence': line_conf < 60.0
                }
                for w in line_text.split()
            ]
            confidence_details.append({
                'line_number': idx + 1,
                'text': line_text,
                'confidence': line_conf,
                'words': words_data
            })

        return {
            'text': full_text,
            'confidence': avg_confidence,
            'duration': round(duration, 3),
            'line_count': len(recognized_lines),
            'provider': 'trocr',
            'confidence_details': confidence_details,
        }
