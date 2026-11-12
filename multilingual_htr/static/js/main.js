// Multilingual HTR - Main JavaScript helper utilities

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        }, 5000);
    });

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // Global copy-to-clipboard handler
    document.querySelectorAll('[data-copy-target]').forEach(button => {
        button.addEventListener('click', () => {
            const targetSelector = button.getAttribute('data-copy-target');
            const targetEl = document.querySelector(targetSelector);
            if (targetEl) {
                const text = targetEl.value !== undefined ? targetEl.value : targetEl.innerText;
                navigator.clipboard.writeText(text).then(() => {
                    const originalHtml = button.innerHTML;
                    button.innerHTML = '<i class="bi bi-check2"></i> Copied!';
                    button.classList.add('btn-success');
                    button.classList.remove('btn-outline-primary', 'btn-outline-secondary');
                    setTimeout(() => {
                        button.innerHTML = originalHtml;
                        button.classList.remove('btn-success');
                        button.classList.add('btn-outline-secondary');
                    }, 2000);
                }).catch(err => {
                    console.error('Copy failed:', err);
                });
            }
        });
    });
});
