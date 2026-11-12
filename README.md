# Multilingual Handwritten and Printed Text Recognition System

A production-ready Django web application engineered for **Multilingual Handwritten Text Recognition (HTR)** and **Optical Character Recognition (OCR)**. Supports English and Indian languages with **Telugu (తెలుగు)** and **Hindi (हिन्दी)** as priority scripts alongside Tamil, Kannada, Marathi, and Bengali.

Powered by a modular OCR service layer integrating **EasyOCR** (local deep learning), **TrOCR** (Hugging Face Transformers for English handwriting), and optional **Google Cloud Vision** (cloud document text detection), coupled with an **OpenCV preprocessing pipeline** and **pypdfium2 multi-page PDF processing**.

Please refer to the full documentation and source code in the [`multilingual_htr/`](multilingual_htr/) directory.

### Quick Start on Windows

```powershell
.\run_local.ps1
```

Or step-by-step:
```powershell
cd multilingual_htr
python manage.py migrate
python manage.py seed_demo_data
python manage.py test
python manage.py runserver 127.0.0.1:8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

- **Admin Login**: `admin` / `AdminPass123!`
- **Demo Student Login**: `student` / `StudentPass123!`
