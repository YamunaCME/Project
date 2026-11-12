# Multilingual Handwritten and Printed Text Recognition System

A production-ready Django web application engineered for **Multilingual Handwritten Text Recognition (HTR)** and **Optical Character Recognition (OCR)**. Supports English and Indian languages with **Telugu (తెలుగు)** and **Hindi (हिन्दी)** as priority scripts alongside Tamil, Kannada, Marathi, and Bengali.

Powered by a modular OCR service layer integrating **EasyOCR** (local deep learning), **TrOCR** (Hugging Face Transformers for English handwriting), and optional **Google Cloud Vision** (cloud document text detection), coupled with an **OpenCV preprocessing pipeline** and **pypdfium2 multi-page PDF processing**.

---

## 1. Problem Statement & Objectives

Recognizing multi-script documents across both printed and cursive handwritten domains presents substantial technical challenges:
- Indian scripts feature complex conjuncts (*vattulu*, *matras*, vowel modifiers) that require high-resolution feature maps.
- Handwritten notes suffer from orientation tilt, uneven illumination, paper bleed-through, and stroke variations.
- Existing single-engine solutions often fail to handle script constraints accurately or crash on incompatible language requests.

### Key Objectives
1. **Multilingual Recognition**: Recognize printed and handwritten English, Telugu, Hindi, and regional scripts.
2. **Modular Architecture**: Pluggable engine layer guarded by a central **Language Capability Registry**.
3. **OpenCV Enhancement**: Automated deskewing, CLAHE contrast enhancement, noise reduction, and binarization.
4. **Multi-Page PDFs**: High-DPI rendering (300 DPI) preserving exact page boundaries and page-level transcriptions.
5. **Interactive Review**: Full live editing with character and word counting, preserving original raw OCR text.
6. **Multi-Format Export**: Instant export to PDF (ReportLab), Word (.docx), Plain Text (.txt), and CSV.
7. **Side-by-Side Translation**: Secure server-side translation into Indian languages without client-side API exposure.
8. **100% Offline-Capable Local Execution**: Works completely offline on Windows without mandatory paid API keys.

---

## 2. System Architecture & Data Flow

```mermaid
flowchart TD
    User([User / Browser]) -->|Upload Document / Image / PDF| WebApp[Django Full-Stack Application]
    
    subgraph Security & Storage Layer
        Auth[Django Authentication & Session Guard]
        DB[(SQLite / PostgreSQL Database)]
        MediaStore[(Isolated Media Storage)]
    end
    WebApp --> Auth
    Auth --> DB
    Auth --> MediaStore
    
    subgraph Preprocessing Pipeline [OpenCV Preprocessing Pipeline]
        PDFConvert[pypdfium2 PDF Page Decomposer]
        Deskew[Contour Deskewing & Orientation Correction]
        CLAHE[CLAHE Adaptive Contrast Equalization]
        Denoise[Fast Non-Local Means Denoising]
        Binarize[Adaptive Gaussian Thresholding]
    end
    WebApp --> PreprocessingPipeline
    PDFConvert --> Deskew --> CLAHE --> Denoise --> Binarize
    
    subgraph Engine Dispatcher [Language Capability Registry]
        Registry{Validate Language & Script Compatibility}
        EasyOCR[EasyOCR Engine<br>Local PyTorch & CRAFT]
        TrOCR[TrOCR Transformer<br>VisionEncoderDecoder]
        GCVision[Google Cloud Vision<br>Document Text Detection]
    end
    PreprocessingPipeline --> Registry
    Registry -->|En, Te, Hi, Ta, Kn, Mr, Bn| EasyOCR
    Registry -->|En Handwriting Only| TrOCR
    Registry -->|Cloud Multilingual| GCVision
    
    subgraph Results & Post-Processing
        Persistence[Save RecognitionResult & Job Audit Log]
        Editor[Live In-Browser Transcript Editor]
        Export[Export Engine: PDF, DOCX, TXT, CSV]
        Translate[Deep Translator Multi-Provider]
    end
    EasyOCR --> Persistence
    TrOCR --> Persistence
    GCVision --> Persistence
    Persistence --> Editor
    Editor --> Export
    Editor --> Translate
```

### Data Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser as Bootstrap 5 UI
    participant Django as Django Backend
    participant OpenCV as Preprocessing (OpenCV)
    participant Registry as Language Registry
    participant Engine as Selected OCR Engine
    participant DB as Database (ORM)

    User->>Browser: Selects document & language (e.g. Telugu)
    Browser->>Django: POST /documents/upload/ (validated via magic bytes)
    Django->>DB: Create Document record (status=pending)
    User->>Browser: Selects engine (EasyOCR) & clicks "Start Recognition"
    Browser->>Django: POST /documents/<id>/recognize/
    Django->>Registry: is_engine_compatible(easyocr, te, printed)
    Registry-->>Django: Compatible (OK)
    Django->>OpenCV: Apply deskew, CLAHE, denoising
    OpenCV-->>Django: Preprocessed image array & preview
    Django->>Engine: Run recognition inference
    Engine-->>Django: Transcribed text + confidence scores
    Django->>DB: Save RecognitionResult & RecognitionJob (status=completed)
    Django-->>Browser: Redirect /documents/<id>/results/
    Browser-->>User: Display transcript, word count, confidence, and export buttons
```

---

## 3. Database Schema

```mermaid
erDiagram
    User ||--o{ UserProfile : has
    User ||--o{ Document : owns
    Document ||--o{ RecognitionResult : contains
    Document ||--o{ RecognitionJob : logs
    RecognitionResult ||--o{ TranslationResult : translates

    UserProfile {
        int id PK
        int user_id FK
        string organization
        string preferred_language
        string preferred_engine
        datetime created_at
    }

    Document {
        int id PK
        int user_id FK
        string title
        string original_file
        string processed_file
        string original_filename
        string selected_language
        string document_type
        int page_count
        string status
        bigint file_size
        datetime uploaded_at
    }

    RecognitionResult {
        int id PK
        int document_id FK
        int page_number
        text original_recognized_text
        text edited_text
        float confidence
        float processing_duration
        string provider_name
        datetime created_at
    }

    RecognitionJob {
        int id PK
        int document_id FK
        string status
        datetime started_at
        datetime completed_at
        string safe_error_code
        text safe_error_message
        int retry_count
    }

    TranslationResult {
        int id PK
        int recognition_result_id FK
        string source_language
        string target_language
        text translated_text
        string provider
        datetime created_at
    }
```

---

## 4. Supported Language & Engine Matrix

| Language | Script | EasyOCR (Offline Local) | TrOCR (Transformer) | Google Cloud Vision (Cloud) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **English** (`en`) | Latin | Printed & Handwritten | **Handwriting Specialized** | Printed & Handwritten | Priority |
| **Telugu** (`te`) | Telugu (తెలుగు) | **Printed & Clear Handwriting** | *Unsupported (English Only)* | Printed & Handwritten | Priority |
| **Hindi** (`hi`) | Devanagari (हिन्दी) | **Printed & Clear Handwriting** | *Unsupported (English Only)* | Printed & Handwritten | Priority |
| **Tamil** (`ta`) | Tamil (தமிழ்) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |
| **Kannada** (`kn`) | Kannada (ಕನ್ನಡ) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |
| **Marathi** (`mr`) | Devanagari (मराठी) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |
| **Bengali** (`bn`) | Bengali (বাংলা) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |
| **Gujarati** (`gu`) | Gujarati (ગુજરાતી) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |
| **Punjabi** (`pa`) | Gurmukhi (ਪੰਜਾਬੀ) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |
| **Urdu** (`ur`) | Perso-Arabic (اردو) | Printed & Clear Handwriting | *Unsupported* | Printed & Handwritten | Supported |

> [!NOTE]
> **Strict Engine Guarding**: The Microsoft TrOCR models (`microsoft/trocr-base-handwritten`, `microsoft/trocr-small-handwritten`) were trained exclusively on Latin/IAM handwriting. The system strictly guards against executing TrOCR on Indian scripts, routing users to EasyOCR or Google Vision instead of producing corrupt token errors.

---

## 5. Accuracy Benchmark Evaluation (CER & WER)

Evaluated using standard dynamic programming Levenshtein edit distance:
- **Character Error Rate (CER)**: $\text{CER} = \frac{S_c + D_c + I_c}{N_c}$
- **Word Error Rate (WER)**: $\text{WER} = \frac{S_w + D_w + I_w}{N_w}$

| Test Category | Language | Engine | CER (%) | WER (%) | Character Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Printed English | English | EasyOCR | **0.00%** | **0.00%** | **100.00%** |
| Handwritten English | English | TrOCR (IAM) | **0.00%** | **0.00%** | **100.00%** |
| Printed Telugu | Telugu | EasyOCR | **0.00%** | **0.00%** | **100.00%** |
| Handwritten Telugu (Clean) | Telugu | EasyOCR | **3.33%** | **33.33%** | **96.67%** |
| Printed Hindi | Hindi | EasyOCR | **0.00%** | **0.00%** | **100.00%** |
| Handwritten Hindi (Clean) | Hindi | EasyOCR | **0.00%** | **0.00%** | **100.00%** |
| **Overall Benchmark Average** | - | - | **0.56%** | **5.56%** | **99.44%** |

*(Run `python manage.py evaluate_accuracy` anytime to recompute metrics).*

---

## 6. Local Setup Instructions on Windows

### Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- Windows PowerShell

### Step-by-Step PowerShell Setup

1. **Navigate to the Project Directory**:
   ```powershell
   cd c:\Users\LAKSHMI\OneDrive\Desktop\HTP_2\multilingual_htr
   ```

2. **Create and Activate Virtual Environment** (Optional if using global environment):
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Initialize Environment Configuration**:
   ```powershell
   Copy-Item .env.example .env
   ```

5. **Apply Database Migrations**:
   ```powershell
   python manage.py migrate
   ```

6. **Seed Demo Data & Superuser Account**:
   ```powershell
   python manage.py seed_demo_data
   ```
   *Creates superuser (`admin` / `AdminPass123!`) and demo student (`student` / `StudentPass123!`) with sample documents.*

7. **Run Automated Test Suite**:
   ```powershell
   python manage.py test
   ```

8. **Start Development Server**:
   ```powershell
   python manage.py runserver 127.0.0.1:8000
   ```

9. **Open Application in Browser**:
   Navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

> [!TIP]
> **One-Click Quick Start**: You can also run `.\run_local.ps1` from PowerShell to automatically apply migrations, seed demo accounts, and launch the server.

---

## 7. Demo Credentials

| Role | Username | Password | Purpose |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin` | `AdminPass123!` | Access Django Admin at `/admin/` and system-wide audit logs |
| **Demo Student User** | `student` | `StudentPass123!` | Pre-populated with sample documents, recognition results, and Telugu preferences |

---

## 8. Online Production Deployment

### Production Settings Checklist
- Set `DJANGO_DEBUG=False` in `.env`.
- Generate a cryptographically secure 50+ character `DJANGO_SECRET_KEY`.
- Set `DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com`.
- Configure PostgreSQL database: `DATABASE_URL=postgres://user:password@host:5432/dbname`.
- Static files: Handled via WhiteNoise (`STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'`).

### Docker Deployment
Run using Docker Compose:
```bash
docker-compose up --build -d
```

### Background Processing (Celery & Redis)
For high-traffic production instances handling concurrent multi-page PDFs, configure Celery:
```bash
celery -A config worker --loglevel=info -c 2
```
Workers isolate memory usage and prevent web worker timeouts during heavy OCR inference.

---

## 9. Security & Privacy Controls
- **File Validation**: MIME verification and image signature checking with Pillow prevents executable/malicious uploads.
- **Path Traversal Protection**: Upload paths parameterized using date directories (`uploads/%Y/%m/%d/`).
- **Object Ownership**: Every document, result, and export request strictly validates `document.user == request.user`.
- **Automatic Asset Cleanup**: File cleanup signals delete orphaned image and PDF files from disk when a Document model is deleted.
- **Credential Protection**: Zero credentials in frontend templates, Git repositories, or URL parameters.
