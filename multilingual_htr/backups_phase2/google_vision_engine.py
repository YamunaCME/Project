"""
Google Cloud Vision Engine Implementation.

Cloud document text detection supporting multilingual printed and handwritten recognition.
Maintains secure credential checks and structured exception handling.
"""

import os
import io
import time
from typing import Dict, Any
from PIL import Image
import numpy as np
import cv2
from django.conf import settings


class GoogleVisionEngine:
    @classmethod
    def is_configured(cls) -> bool:
        """Checks whether Google Cloud credentials or project are present."""
        cred_path = getattr(settings, 'GOOGLE_APPLICATION_CREDENTIALS', None) or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if cred_path and os.path.exists(cred_path):
            return True
        # Check standard default auth
        return bool(os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))

    @classmethod
    def recognize(
        cls,
        image_input,
        language_code: str = 'en',
        document_type: str = 'printed',
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes document text detection through Google Cloud Vision API.
        """
        if not cls.is_configured():
            raise RuntimeError(
                "Google Cloud Vision is not configured. "
                "Please configure GOOGLE_APPLICATION_CREDENTIALS in your .env file "
                "or select EasyOCR (local offline engine)."
            )

        try:
            from google.cloud import vision
            from google.cloud.vision_v1 import types
        except ImportError:
            raise RuntimeError(
                "google-cloud-vision package is not installed. Run 'pip install google-cloud-vision'."
            )

        start_time = time.time()

        # Convert image input to bytes
        if isinstance(image_input, str):
            with open(image_input, 'rb') as f:
                content = f.read()
        elif isinstance(image_input, Image.Image):
            byte_io = io.BytesIO()
            image_input.save(byte_io, format='JPEG', quality=95)
            content = byte_io.getvalue()
        elif isinstance(image_input, np.ndarray):
            # Encode numpy image as JPEG bytes
            success, buffer = cv2.imencode('.jpg', image_input)
            if not success:
                raise ValueError("Failed to encode image array to bytes.")
            content = buffer.tobytes()
        else:
            raise ValueError("Unsupported image input type for Google Cloud Vision.")

        try:
            client = vision.ImageAnnotatorClient()
            image = types.Image(content=content)

            # Language hint
            image_context = types.ImageContext(language_hints=[language_code])

            # Perform document text detection (optimized for dense document layouts)
            response = client.document_text_detection(image=image, image_context=image_context)

            if response.error.message:
                raise RuntimeError(f"Google Cloud Vision API Error: {response.error.message}")

            full_text = response.full_text_annotation.text if response.full_text_annotation else ""

            # Calculate average confidence across pages and blocks
            confidences = []
            if response.full_text_annotation and response.full_text_annotation.pages:
                for page in response.full_text_annotation.pages:
                    if hasattr(page, 'confidence') and page.confidence > 0:
                        confidences.append(page.confidence)
                    for block in page.blocks:
                        if hasattr(block, 'confidence') and block.confidence > 0:
                            confidences.append(block.confidence)

            avg_conf = round(float(sum(confidences) / len(confidences) * 100.0), 2) if confidences else 90.0
            duration = time.time() - start_time

            return {
                'text': full_text.strip(),
                'confidence': avg_conf,
                'duration': round(duration, 3),
                'provider': 'google_vision',
                'confidence_details': [],
            }

        except Exception as e:
            err_msg = str(e).lower()
            if "credentials" in err_msg or "auth" in err_msg:
                raise RuntimeError(
                    f"Google Cloud Authentication Failure: {str(e)}. "
                    "Verify your service account key file permissions and path."
                )
            if "quota" in err_msg or "429" in err_msg or "resource_exhausted" in err_msg:
                raise RuntimeError(
                    "Google Cloud Vision API quota limit exceeded (429 Resource Exhausted). "
                    "Please switch to EasyOCR (local offline engine) which runs without API quotas."
                )
            raise RuntimeError(f"Google Cloud Vision API request failed: {str(e)}")
