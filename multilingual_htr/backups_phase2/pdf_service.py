"""
PDF Processing Service using pypdfium2.

Renders PDF pages into high-resolution images for OCR ingestion,
preserving page count and boundaries without external system binaries.
"""

import os
from typing import List, Tuple
from PIL import Image
import pypdfium2 as pdfium


class PDFService:
    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """Returns total number of pages in PDF document."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        pdf = None
        try:
            pdf = pdfium.PdfDocument(pdf_path)
            count = len(pdf)
            return count
        except Exception as e:
            raise ValueError(f"Failed to read PDF page count: {str(e)}")
        finally:
            if pdf is not None:
                try:
                    pdf.close()
                except Exception:
                    pass

    @staticmethod
    def render_pages_to_images(
        pdf_path: str,
        max_pages: int = 15,
        dpi: int = 300,
        return_meta: bool = False
    ):
        """
        Renders PDF pages into PIL Images.
        Returns:
            - List of (page_number_1_indexed, PIL.Image) if return_meta=False
            - (results, total_pages, is_truncated) if return_meta=True
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        pdf = None
        try:
            pdf = pdfium.PdfDocument(pdf_path)
            total_pages = len(pdf)
            if total_pages == 0:
                raise ValueError("PDF document contains no readable pages.")

            render_count = min(total_pages, max_pages)
            is_truncated = total_pages > max_pages

            results: List[Tuple[int, Image.Image]] = []
            scale = dpi / 72.0  # 72 is standard PDF point unit

            for i in range(render_count):
                page = pdf[i]
                # Render to high-DPI bitmap
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
                results.append((i + 1, pil_image))

            if return_meta:
                return results, total_pages, is_truncated
            return results
        except Exception as e:
            raise RuntimeError(f"Error rendering PDF pages: {str(e)}")
        finally:
            if pdf is not None:
                try:
                    pdf.close()
                except Exception:
                    pass
