"""
OpenCV Image Preprocessing Pipeline for Multilingual HTR.

Applies configurable operations:
- Grayscale conversion
- Contrast Limited Adaptive Histogram Equalization (CLAHE)
- Deskewing / orientation correction
- Denoising / Gaussian filtering
- Adaptive binarization / thresholding
Original document files are always preserved intact.
"""

import os
import cv2
import numpy as np
from PIL import Image
from typing import Tuple, Optional, Dict, Any


class PreprocessingPipeline:
    @staticmethod
    def deskew_image(image: np.ndarray) -> np.ndarray:
        """
        Detects text line orientation angle and rotates the image to horizontal.
        Limits rotation to [-15, 15] degrees to avoid inverted or vertical flipping.
        """
        try:
            # Convert to gray if 3-channel
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # Invert colors: text as foreground (white)
            inv = cv2.bitwise_not(gray)
            thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

            # Find coordinates of all foreground pixels in (x, y) order
            coords = np.column_stack(np.where(thresh > 0)[::-1])
            if len(coords) < 100:
                return image

            rect = cv2.minAreaRect(coords)
            (w_rect, h_rect) = rect[1]
            angle = rect[2]

            # In OpenCV 4.5+, angle is in [-90, 0) or [0, 90)
            if w_rect < h_rect:
                angle = -(90.0 - angle) if angle > 0 else angle + 90.0
            else:
                angle = -angle if angle > 0 else angle

            # Only correct gentle scanning tilt within [-15, 15] degrees
            # Beyond 15 degrees is usually non-text borders, margins, or vertical artwork
            if abs(angle) < 0.5 or abs(angle) > 15.0:
                return image

            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                image, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            return rotated
        except Exception:
            return image

    @staticmethod
    def normalize_illumination(gray: np.ndarray, kernel_size: int = 51) -> np.ndarray:
        """
        Removes harsh non-uniform shadows and lighting gradients via morphological background division.
        Essential for mobile camera captures of notebook pages and cursive handwriting.
        """
        try:
            k = max(15, kernel_size if kernel_size % 2 == 1 else kernel_size + 1)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
            background = cv2.morphologyEx(gray, cv2.MORPH_DILATE, kernel)
            normalized = cv2.divide(gray, background, scale=255)
            return normalized
        except Exception:
            return gray

    @staticmethod
    def sharpen_handwriting(gray: np.ndarray) -> np.ndarray:
        """
        Enhances edge definition and ink contrast of faint ballpoint/pencil cursive strokes.
        """
        try:
            gaussian = cv2.GaussianBlur(gray, (0, 0), 2.0)
            sharpened = cv2.addWeighted(gray, 1.4, gaussian, -0.4, 0)
            return np.clip(sharpened, 0, 255).astype(np.uint8)
        except Exception:
            return gray

    @classmethod
    def apply(
        cls,
        image_input,
        options: Optional[Dict[str, Any]] = None,
        save_path: Optional[str] = None
    ) -> Tuple[np.ndarray, Optional[str]]:
        """
        Processes image according to provided configuration options.

        :param image_input: File path (str) or numpy ndarray or PIL Image.
        :param options: Dict of options {apply_deskew, apply_illumination, apply_clahe, apply_sharpening, apply_denoising, apply_threshold}
        :param save_path: Optional path to save the preprocessed preview.
        :return: (processed_numpy_bgr_or_rgb, saved_filepath)
        """
        if options is None:
            options = {
                'apply_deskew': True,
                'apply_illumination': True,
                'apply_clahe': True,
                'apply_sharpening': True,
                'apply_denoising': False,
                'apply_threshold': False,
            }

        # Load input into numpy array
        if isinstance(image_input, str):
            image = cv2.imread(image_input)
            if image is None:
                # Try Pillow in case of unicode filename issues on Windows
                with Image.open(image_input) as pil_img:
                    image = cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)
        elif isinstance(image_input, Image.Image):
            image = cv2.cvtColor(np.array(image_input.convert('RGB')), cv2.COLOR_RGB2BGR)
        elif isinstance(image_input, np.ndarray):
            image = image_input.copy()
        else:
            raise ValueError("Unsupported image input type.")

        if image is None or image.size == 0:
            raise ValueError("Empty or invalid image data.")

        # 0. High-resolution scaling optimization (prevents multi-minute CPU lag on 4K+ phone photos)
        max_dim = options.get('max_dimension', 1800)
        h, w = image.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w, new_h = int(w * scale), int(h * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # 1. Deskew if enabled
        if options.get('apply_deskew', True):
            image = cls.deskew_image(image)

        # 2. Convert to grayscale for enhancement steps
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # 3. Illumination / Shadow Normalization (critical for uneven notebook photos)
        if options.get('apply_illumination', True):
            gray = cls.normalize_illumination(gray, kernel_size=51)

        # 4. Denoising
        if options.get('apply_denoising', False):
            # Fast Non-Local Means Denoising on grayscale
            gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

        # 5. Contrast Enhancement (CLAHE)
        if options.get('apply_clahe', True):
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        # 6. Sharpening faint strokes
        if options.get('apply_sharpening', False):
            gray = cls.sharpen_handwriting(gray)

        # 7. Thresholding / Binarization
        if options.get('apply_threshold', False):
            # Adaptive Gaussian Thresholding
            gray = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 8
            )

        # Convert back to 3-channel BGR for consistent preview and OCR ingestion
        processed_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        # 6. Save preview and intermediate steps if path supplied
        saved_file_path = None
        if save_path:
            save_dir = os.path.dirname(save_path)
            os.makedirs(save_dir, exist_ok=True)
            
            # Step 1: Original input image
            try:
                orig_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if len(image.shape) == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
                Image.fromarray(orig_rgb).save(os.path.join(save_dir, "step1_original.jpg"), format='JPEG', quality=92)
            except Exception:
                pass

            # Step 2: Illumination normalized & enhanced
            try:
                enh_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
                Image.fromarray(enh_rgb).save(os.path.join(save_dir, "step2_enhanced.jpg"), format='JPEG', quality=92)
            except Exception:
                pass

            # Step 3: Final OCR input image
            rgb_result = cv2.cvtColor(processed_bgr, cv2.COLOR_BGR2RGB)
            pil_save = Image.fromarray(rgb_result)
            pil_save.save(save_path, format='JPEG', quality=92)
            try:
                pil_save.save(os.path.join(save_dir, "step3_ocr_input.jpg"), format='JPEG', quality=92)
            except Exception:
                pass
            saved_file_path = save_path

        return processed_bgr, saved_file_path
