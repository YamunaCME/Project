"""
Export Service for Multilingual HTR.

Generates downloadable export files across 4 formats:
- PDF (ReportLab)
- Microsoft Word (python-docx)
- Plain Text (TXT)
- Structured Spreadsheet (CSV)
"""

import io
import csv
import os
from typing import List
from django.utils import timezone
from docx import Document as DocxDocument
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from documents.models import Document, RecognitionResult, TranslationResult

# Register Unicode Indic TrueType Font (Nirmala.ttc) for Telugu, Hindi, and English PDF rendering
UNICODE_FONT_NAME = 'Helvetica'
try:
    nirmala_path = r'C:\Windows\Fonts\Nirmala.ttc'
    if os.path.exists(nirmala_path):
        pdfmetrics.registerFont(TTFont('Nirmala', nirmala_path, subfontIndex=0))
        UNICODE_FONT_NAME = 'Nirmala'
except Exception:
    pass


class ExportService:
    @staticmethod
    def export_txt(document: Document) -> io.BytesIO:
        """Generates UTF-8 encoded plain text export."""
        output = io.StringIO()
        output.write(f"DOCUMENT RECOGNITION TRANSCRIPT\n")
        output.write(f"Title: {document.title}\n")
        output.write(f"Language: {document.selected_language}\n")
        output.write(f"Type: {document.get_document_type_display()}\n")
        output.write(f"Exported Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        output.write("=" * 60 + "\n\n")

        results = document.results.all().order_by('page_number')
        for res in results:
            if document.page_count > 1:
                output.write(f"--- PAGE {res.page_number} (Engine: {res.provider_name}, Confidence: {res.confidence}%) ---\n\n")
            output.write(res.effective_text)
            output.write("\n\n")

        byte_io = io.BytesIO()
        byte_io.write(output.getvalue().encode('utf-8'))
        byte_io.seek(0)
        return byte_io

    @staticmethod
    def export_csv(document: Document) -> io.BytesIO:
        """Generates CSV spreadsheet export with page-level metrics."""
        byte_io = io.BytesIO()
        # Add UTF-8 BOM so Excel opens Indian language scripts properly
        byte_io.write(b'\xef\xbb\xbf')

        text_stream = io.StringIO()
        writer = csv.writer(text_stream)
        writer.writerow([
            'Document Title',
            'Page Number',
            'Language',
            'Engine Provider',
            'Confidence (%)',
            'Word Count',
            'Character Count',
            'Transcribed Text'
        ])

        results = document.results.all().order_by('page_number')
        for res in results:
            writer.writerow([
                document.title,
                res.page_number,
                document.selected_language,
                res.provider_name,
                f"{res.confidence:.1f}" if res.confidence is not None else "N/A",
                res.word_count,
                res.char_count,
                res.effective_text
            ])

        byte_io.write(text_stream.getvalue().encode('utf-8'))
        byte_io.seek(0)
        return byte_io

    @staticmethod
    def export_docx(document: Document) -> io.BytesIO:
        """Generates formatted Microsoft Word (.docx) document with Indic font support."""
        doc = DocxDocument()

        # Set default font to Nirmala UI for native Telugu, Hindi, and English glyph shaping
        style = doc.styles['Normal']
        style.font.name = 'Nirmala UI'

        # Document Title
        title_heading = doc.add_heading(document.title, level=0)
        title_heading.style.font.name = 'Nirmala UI'

        # Metadata Table
        meta_table = doc.add_table(rows=4, cols=2)
        meta_table.style = 'Light Shading Accent 1'
        meta_data = [
            ("Original Filename", document.original_filename),
            ("Document Type", document.get_document_type_display()),
            ("Language Code", document.selected_language.upper()),
            ("Total Pages", str(document.page_count)),
        ]
        for row_idx, (label, val) in enumerate(meta_data):
            row = meta_table.rows[row_idx]
            row.cells[0].text = label
            row.cells[1].text = val

        doc.add_paragraph()  # Spacing

        results = document.results.all().order_by('page_number')
        for res in results:
            if document.page_count > 1:
                p_head = doc.add_heading(f"Page {res.page_number}", level=2)
                p_head.style.font.color.rgb = RGBColor(37, 99, 235)
                meta_p = doc.add_paragraph()
                meta_p.add_run(f"Engine: {res.provider_name.upper()} | Confidence: {res.confidence or 'N/A'}% | Words: {res.word_count}").italic = True

            # Text content
            lines = res.effective_text.split('\n')
            for line in lines:
                if line.strip():
                    p = doc.add_paragraph(line)
                    p.paragraph_format.space_after = Pt(4)

            if document.page_count > 1 and res != results.last():
                doc.add_page_break()

        byte_io = io.BytesIO()
        doc.save(byte_io)
        byte_io.seek(0)
        return byte_io

    @staticmethod
    def export_pdf(document: Document) -> io.BytesIO:
        """Generates formatted PDF report using ReportLab."""
        byte_io = io.BytesIO()
        pdf_doc = SimpleDocTemplate(
            byte_io,
            pagesize=letter,
            rightMargin=45,
            leftMargin=45,
            topMargin=45,
            bottomMargin=45
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=UNICODE_FONT_NAME,
            fontSize=20,
            leading=24,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=12
        )
        meta_style = ParagraphStyle(
            'CustomMeta',
            parent=styles['Normal'],
            fontName=UNICODE_FONT_NAME,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#64748b')
        )
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontName=UNICODE_FONT_NAME,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=8
        )
        page_header_style = ParagraphStyle(
            'PageHeader',
            parent=styles['Heading2'],
            fontName=UNICODE_FONT_NAME,
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#2563eb'),
            spaceBefore=12,
            spaceAfter=6
        )

        elements = []

        # Document Header
        elements.append(Paragraph(f"<b>{document.title}</b>", title_style))
        elements.append(Paragraph(
            f"Transcribed with Multilingual HTR &bull; Language: {document.selected_language.upper()} &bull; "
            f"Type: {document.get_document_type_display()} &bull; Date: {timezone.now().strftime('%b %d, %Y')}",
            meta_style
        ))
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=14))

        results = document.results.all().order_by('page_number')
        for res in results:
            if document.page_count > 1:
                elements.append(Paragraph(f"Page {res.page_number} ({res.provider_name.upper()} - {res.confidence or 'N/A'}% Confidence)", page_header_style))
                elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceAfter=8))

            paragraphs = res.effective_text.split('\n')
            for p_text in paragraphs:
                cleaned = p_text.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                if cleaned:
                    elements.append(Paragraph(cleaned, body_style))
                else:
                    elements.append(Spacer(1, 4))

            elements.append(Spacer(1, 12))

        pdf_doc.build(elements)
        byte_io.seek(0)
        return byte_io

    @staticmethod
    def export_translation_txt(translation: TranslationResult) -> io.BytesIO:
        """Generates UTF-8 encoded plain text export of translated document."""
        output = io.StringIO()
        doc = translation.recognition_result.document
        output.write("DOCUMENT TRANSLATION REPORT\n")
        output.write(f"Document Title: {doc.title}\n")
        output.write(f"Source Language: {translation.source_language.upper()}\n")
        output.write(f"Target Language: {translation.target_language.upper()}\n")
        output.write(f"Translation Provider: {translation.provider}\n")
        output.write(f"Date: {translation.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        output.write("=" * 60 + "\n\n")
        output.write(translation.translated_text)
        output.write("\n")

        byte_io = io.BytesIO()
        byte_io.write(output.getvalue().encode('utf-8'))
        byte_io.seek(0)
        return byte_io
