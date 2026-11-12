// Upload Drag & Drop and Preview Handlers
document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileUploadInput');
    const previewContainer = document.getElementById('uploadPreviewContainer');
    const previewImage = document.getElementById('previewImage');
    const previewPdf = document.getElementById('previewPdf');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const fileSizeDisplay = document.getElementById('fileSizeDisplay');
    const removeBtn = document.getElementById('removeFileBtn');

    if (!dropzone || !fileInput) return;

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Highlight drop area
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add('drag-over'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove('drag-over'), false);
    });

    // Handle dropped files
    dropzone.addEventListener('drop', e => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelect(files[0]);
        }
    });

    // Handle manual file selection
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    function formatBytes(bytes, decimals = 1) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    function handleFileSelect(file) {
        const allowedExtensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.pdf'];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

        if (!allowedExtensions.includes(ext)) {
            alert(`File type '${ext}' is not supported. Please select a JPG, PNG, TIFF, or PDF.`);
            fileInput.value = '';
            return;
        }

        fileNameDisplay.textContent = file.name;
        fileSizeDisplay.textContent = formatBytes(file.size);

        if (ext === '.pdf') {
            previewImage.classList.add('d-none');
            previewPdf.classList.remove('d-none');
        } else {
            previewPdf.classList.add('d-none');
            previewImage.classList.remove('d-none');
            const reader = new FileReader();
            reader.onload = e => {
                previewImage.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        dropzone.classList.add('d-none');
        previewContainer.classList.remove('d-none');
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', () => {
            fileInput.value = '';
            previewContainer.classList.add('d-none');
            dropzone.classList.remove('d-none');
        });
    }
});
