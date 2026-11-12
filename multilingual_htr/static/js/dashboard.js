// Dashboard Chart.js Visualizations
document.addEventListener('DOMContentLoaded', () => {
    // 1. Document Type Chart (Donut)
    const typeCanvas = document.getElementById('docTypeChart');
    if (typeCanvas) {
        const labels = JSON.parse(typeCanvas.dataset.labels || '[]');
        const data = JSON.parse(typeCanvas.dataset.values || '[]');
        const hasData = data.some(val => val > 0);

        new Chart(typeCanvas, {
            type: 'doughnut',
            data: {
                labels: hasData ? labels : ['No Documents Yet'],
                datasets: [{
                    data: hasData ? data : [1],
                    backgroundColor: hasData ? ['#2563eb', '#f59e0b', '#8b5cf6'] : ['#e2e8f0'],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 12, padding: 15 }
                    }
                },
                cutout: '70%'
            }
        });
    }

    // 2. Language Distribution Chart (Bar)
    const langCanvas = document.getElementById('docLangChart');
    if (langCanvas) {
        const labels = JSON.parse(langCanvas.dataset.labels || '[]');
        const data = JSON.parse(langCanvas.dataset.values || '[]');
        const hasData = data.length > 0;

        new Chart(langCanvas, {
            type: 'bar',
            data: {
                labels: hasData ? labels : ['English'],
                datasets: [{
                    label: 'Documents',
                    data: hasData ? data : [0],
                    backgroundColor: '#4f46e5',
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1 }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }
});
