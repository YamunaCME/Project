"""
EasyOCR Engine Implementation.

Provides deep-learning OCR with offline execution, language combinations,
and reusable singleton reader instances to optimize memory and response time.
"""

import os
import time
from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import easyocr
import torch
from django.conf import settings
from .technical_postprocessor import TechnicalPostProcessor


class EasyOCREngine:
    """Singleton-managed EasyOCR engine with multi-language model cache."""

    _readers: Dict[Tuple[str, ...], easyocr.Reader] = {}
    _device: Optional[bool] = None

    @classmethod
    def _get_gpu_support(cls) -> bool:
        if cls._device is None:
            cls._device = torch.cuda.is_available()
        return cls._device

    @classmethod
    def _map_language_code(cls, lang_code: str) -> List[str]:
        """
        Maps ISO 639-1 language code to EasyOCR language identifier list.
        Indian scripts typically benefit from including English ('en') for mixed alphanumeric text.
        """
        lang_code = lang_code.lower().strip()
        # Language mappings for EasyOCR
        mapping = {
            'en': ['en'],
            'te': ['te', 'en'],
            'hi': ['hi', 'en'],
            'ta': ['ta', 'en'],
            'kn': ['kn', 'en'],
            'mr': ['mr', 'en'],
            'bn': ['bn', 'en'],
            'gu': ['gu', 'en'],
            'pa': ['pa', 'en'],
            'ur': ['ur', 'en'],
        }
        return mapping.get(lang_code, ['en'])

    @classmethod
    def get_reader(cls, lang_code: str) -> easyocr.Reader:
        """Retrieves or initializes a reusable EasyOCR Reader for the language."""
        lang_list = cls._map_language_code(lang_code)
        cache_key = tuple(sorted(lang_list))

        if cache_key not in cls._readers:
            gpu_available = cls._get_gpu_support()
            model_storage_directory = getattr(settings, 'EASYOCR_MODEL_DIR', None) or (settings.BASE_DIR / '.EasyOCR' / 'model')
            user_network_directory = getattr(settings, 'EASYOCR_USER_NETWORK_DIR', None) or (settings.BASE_DIR / '.EasyOCR' / 'user_network')
            kwargs = {
                'gpu': gpu_available,
                'verbose': False,
                'model_storage_directory': str(model_storage_directory),
                'user_network_directory': str(user_network_directory),
            }

            cls._readers[cache_key] = easyocr.Reader(
                lang_list,
                **kwargs
            )

        return cls._readers[cache_key]

    @classmethod
    def recognize(
        cls,
        image_input,
        language_code: str = 'en',
        document_type: str = 'printed',
        detail: int = 1
    ) -> Dict[str, Any]:
        """
        Performs OCR on image using EasyOCR.

        :param image_input: File path or numpy image array (BGR or RGB).
        :param language_code: Target document language (e.g., 'en', 'te', 'hi').
        :param document_type: 'printed', 'handwritten', or 'mixed'.
        :param detail: 0 for raw text list, 1 for bounding boxes + confidence.
        :return: Dict containing recognized_text, confidence, duration, lines.
        """
        import cv2
        start_time = time.time()

        if isinstance(image_input, np.ndarray) and (image_input.size == 0 or image_input.shape[0] == 0 or image_input.shape[1] == 0):
            return {
                'text': '',
                'confidence': 0.0,
                'duration': round(time.time() - start_time, 3),
                'line_count': 0,
                'provider': 'easyocr',
                'raw_results': [] if detail == 1 else None,
            }

        reader = cls.get_reader(language_code)

        # Convert OpenCV BGR to RGB if needed
        ocr_input = image_input
        if isinstance(image_input, np.ndarray) and len(image_input.shape) == 3:
            # OpenCV loads images as BGR, convert to RGB for accurate CRAFT/ResNet detection
            ocr_input = cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB)

        # Tune detection thresholds for handwritten documents and lecture notes
        is_handwriting = str(document_type).lower().strip() in ('handwritten', 'mixed', 'academic', 'medical')
        text_threshold = 0.4 if is_handwriting else 0.7
        low_text = 0.3 if is_handwriting else 0.4
        link_threshold = 0.3 if is_handwriting else 0.4
        slope_ths = 0.3 if is_handwriting else 0.1

        # Use batch_size=8 and appropriate mag_ratio to accelerate CPU inference
        mag = 1.0 if (isinstance(ocr_input, np.ndarray) and ocr_input.shape[1] >= 1000) else 1.5

        results = reader.readtext(
            ocr_input,
            detail=1,
            paragraph=False,
            text_threshold=text_threshold,
            low_text=low_text,
            link_threshold=link_threshold,
            slope_ths=slope_ths,
            batch_size=8,
            mag_ratio=mag
        )

        # Get image width to filter edge noise
        img_width = ocr_input.shape[1] if isinstance(ocr_input, np.ndarray) and len(ocr_input.shape) >= 2 else 1000

        # Filter out extreme edge bleed (adjacent notebook page, spiral binder, outer margins)
        # Helper to compute bounding box geometry
        def get_box_geom(item):
            bbox = item[0]
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            return min(xs), max(xs), min(ys), max(ys)

        filtered_results = []
        for item in results:
            bbox, text, conf = item
            cleaned = text.strip()
            if not cleaned:
                continue
            x_min, x_max, y_top, y_bottom = get_box_geom(item)
            # Skip noise fragments on the extreme outer margins (> 81% width with low conf/short len, or < 3% width)
            if x_min > (img_width * 0.81) and (len(cleaned) <= 4 or conf < 0.70):
                continue
            if x_max < (img_width * 0.03) and len(cleaned) <= 2:
                continue
            filtered_results.append(item)

        # Robust Collision-Aware Line Clustering:
        # Prevents artificial column splitting while strictly preventing words at the same
        # horizontal coordinates from merging into the same line.
        sorted_boxes = sorted(filtered_results, key=lambda it: get_box_geom(it)[2])
        lines = []
        for it in sorted_boxes:
            x_min, x_max, y_top, y_bottom = get_box_geom(it)
            y_mid = (y_top + y_bottom) / 2.0
            h = max(1.0, y_bottom - y_top)
            w = max(1.0, x_max - x_min)

            # Match to an existing line if no horizontal collision and vertical center is within span
            matched_line = None
            min_v_dist = 9999.0
            for line in lines:
                # Check horizontal collision: does 'it' overlap horizontally with any existing word in 'line'?
                has_h_collision = False
                for member in line:
                    m_xmin, m_xmax, _, _ = get_box_geom(member)
                    m_w = max(1.0, m_xmax - m_xmin)
                    h_overlap = max(0.0, min(x_max, m_xmax) - max(x_min, m_xmin))
                    if h_overlap > (0.25 * min(w, m_w)):
                        has_h_collision = True
                        break

                if has_h_collision:
                    continue

                line_ymids = [(get_box_geom(item)[2] + get_box_geom(item)[3]) / 2.0 for item in line]
                line_heights = [get_box_geom(item)[3] - get_box_geom(item)[2] for item in line]
                avg_line_y = sum(line_ymids) / len(line_ymids)
                avg_line_h = sum(line_heights) / len(line_heights)

                v_dist = abs(y_mid - avg_line_y)
                if v_dist < (max(h, avg_line_h) * 0.75) and v_dist < min_v_dist:
                    min_v_dist = v_dist
                    matched_line = line

            if matched_line is not None:
                matched_line.append(it)
            else:
                lines.append([it])

        # Sort lines vertically from top to bottom by their vertical centers
        lines.sort(key=lambda l: sum((get_box_geom(item)[2] + get_box_geom(item)[3]) / 2.0 for item in l) / len(l))

        # Within each line, sort boxes horizontally from left to right
        for line in lines:
            line.sort(key=lambda it: min(p[0] for p in it[0]))

        lines_text = []
        confidences = []
        confidence_details = []

        for idx, line_items in enumerate(lines):
            line_str = " ".join(it[1].strip() for it in line_items if it[1].strip())
            if not line_str:
                continue

            lines_text.append(line_str)
            line_confs = [float(it[2]) for it in line_items]
            confidences.extend(line_confs)
            avg_line_conf = round((sum(line_confs) / len(line_confs)) * 100.0, 1) if line_confs else 0.0

            words_data = []
            for it in line_items:
                w_conf = round(float(it[2]) * 100.0, 1)
                for w in it[1].strip().split():
                    words_data.append({
                        'word': w,
                        'confidence': w_conf,
                        'is_low_confidence': w_conf < 60.0
                    })

            confidence_details.append({
                'line_number': len(lines_text),
                'text': line_str,
                'confidence': avg_line_conf,
                'words': words_data
            })

        duration = time.time() - start_time
        raw_full_text = "\n".join(lines_text)

        # Apply technical & code post-processor for handwritten, academic, or technical notes
        doc_type_str = str(document_type).lower().strip()
        should_clean = is_handwriting or doc_type_str in ('academic', 'mixed') or TechnicalPostProcessor.is_code_line(raw_full_text)
        cleaned_text = TechnicalPostProcessor.post_process(raw_full_text) if should_clean else raw_full_text

        # Calculate average confidence percentage (0.0 to 100.0)
        if confidences:
            avg_confidence = round((sum(confidences) / len(confidences)) * 100.0, 2)
        else:
            avg_confidence = 0.0

        return {
            'text': cleaned_text,
            'raw_text': raw_full_text,
            'confidence': avg_confidence,
            'duration': round(duration, 3),
            'line_count': len(lines_text),
            'provider': 'easyocr',
            'confidence_details': confidence_details,
            'raw_results': results if detail == 1 else None,
        }
