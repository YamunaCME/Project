// Results Page Character and Word Counter, Confidence Toggle, and In-Page Translation
document.addEventListener('DOMContentLoaded', () => {
    // 1. Live Word and Character Counting
    const textarea = document.querySelector('.ocr-editor-textarea');
    const wordCountSpan = document.getElementById('liveWordCount');
    const charCountSpan = document.getElementById('liveCharCount');

    function updateCounts() {
        if (!textarea) return;
        const text = textarea.value.trim();
        const words = text ? text.split(/\s+/).length : 0;
        const chars = text.length;

        if (wordCountSpan) wordCountSpan.textContent = words;
        if (charCountSpan) charCountSpan.textContent = chars;
    }

    if (textarea) {
        textarea.addEventListener('input', updateCounts);
        updateCounts();
    }

    // 2. Toggle Uncertain Words Confidence Breakdown
    const toggleConfidenceBtn = document.getElementById('toggleConfidenceBtn');
    const confidenceBox = document.getElementById('confidenceInspectionBox');
    if (toggleConfidenceBtn && confidenceBox) {
        toggleConfidenceBtn.addEventListener('click', () => {
            confidenceBox.classList.toggle('d-none');
            const isVisible = !confidenceBox.classList.contains('d-none');
            toggleConfidenceBtn.classList.toggle('btn-warning', isVisible);
            toggleConfidenceBtn.classList.toggle('btn-outline-warning', !isVisible);
        });
    }

    // 3. In-Page Translation Form with AJAX
    const translateForm = document.getElementById('quickTranslateForm');
    const translateBtn = document.getElementById('translateBtn');
    const translateBtnSpinner = document.getElementById('translateBtnSpinner');
    const translateBtnIcon = document.getElementById('translateBtnIcon');
    const translationResultBox = document.getElementById('translationResultBox');
    const translationOutputText = document.getElementById('translationOutputText');
    const translationTargetLang = document.getElementById('translationTargetLang');
    const translationProvider = document.getElementById('translationProvider');
    const translationAlert = document.getElementById('translationAlert');

    if (translateForm) {
        translateForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(translateForm);
            const targetLang = formData.get('target_language');

            if (!targetLang) {
                if (translationAlert) {
                    translationAlert.textContent = 'Please choose a target language first.';
                    translationAlert.classList.remove('d-none');
                }
                return;
            }

            if (translationAlert) translationAlert.classList.add('d-none');
            if (translateBtn) translateBtn.disabled = true;
            if (translateBtnSpinner) translateBtnSpinner.classList.remove('d-none');
            if (translateBtnIcon) translateBtnIcon.classList.add('d-none');

            try {
                const response = await fetch(translateForm.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    if (translationOutputText) translationOutputText.textContent = data.translated_text;
                    if (translationTargetLang) translationTargetLang.textContent = data.target_language;
                    if (translationProvider) translationProvider.textContent = data.provider;
                    if (translationResultBox) translationResultBox.classList.remove('d-none');
                } else {
                    if (translationAlert) {
                        translationAlert.textContent = data.error || 'Translation request failed. Please retry.';
                        translationAlert.classList.remove('d-none');
                    }
                }
            } catch (err) {
                if (translationAlert) {
                    translationAlert.textContent = 'Network error or server timeout. Please try again.';
                    translationAlert.classList.remove('d-none');
                }
            } finally {
                if (translateBtn) translateBtn.disabled = false;
                if (translateBtnSpinner) translateBtnSpinner.classList.add('d-none');
                if (translateBtnIcon) translateBtnIcon.classList.remove('d-none');
            }
        });
    }

    // 4. Source Document Viewer Controls (Zoom, Rotate, Toggle Original/Preprocessed)
    const viewerImage = document.getElementById('viewerImage');
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');
    const rotateBtn = document.getElementById('rotateBtn');
    const resetImgBtn = document.getElementById('resetImgBtn');
    const toggleImageVersionBtn = document.getElementById('toggleImageVersionBtn');
    const imageVersionLabel = document.getElementById('imageVersionLabel');

    let currentScale = 1.0;
    let currentRotation = 0;

    function applyTransforms() {
        if (!viewerImage) return;
        viewerImage.style.transform = `scale(${currentScale}) rotate(${currentRotation}deg)`;
    }

    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => {
            currentScale = Math.min(3.0, currentScale + 0.25);
            applyTransforms();
        });
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => {
            currentScale = Math.max(0.5, currentScale - 0.25);
            applyTransforms();
        });
    }
    if (rotateBtn) {
        rotateBtn.addEventListener('click', () => {
            currentRotation = (currentRotation + 90) % 360;
            applyTransforms();
        });
    }
    if (resetImgBtn) {
        resetImgBtn.addEventListener('click', () => {
            currentScale = 1.0;
            currentRotation = 0;
            applyTransforms();
        });
    }
    if (toggleImageVersionBtn && viewerImage) {
        let isProcessed = true;
        toggleImageVersionBtn.addEventListener('click', () => {
            const originalUrl = viewerImage.getAttribute('data-original-url');
            const processedUrl = viewerImage.getAttribute('data-processed-url');
            if (!processedUrl || !originalUrl) return;

            isProcessed = !isProcessed;
            viewerImage.src = isProcessed ? processedUrl : originalUrl;
            if (imageVersionLabel) {
                imageVersionLabel.textContent = isProcessed ? 'Processed' : 'Original';
            }
            toggleImageVersionBtn.classList.toggle('btn-primary', !isProcessed);
            toggleImageVersionBtn.classList.toggle('btn-outline-primary', isProcessed);
        });
    }
});
