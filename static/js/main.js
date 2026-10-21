// static/js/main.js — JavaScript customizado mínimo
// ================================================

// Inicializa tooltips (se usar)
document.addEventListener('DOMContentLoaded', () => {
    // Auto-focus no primeiro input de formulários HTMX
    document.body.addEventListener('htmx:afterSwap', (evt) => {
        const modal = evt.target.querySelector('[x-data*="modal"]');
        if (modal) {
            const input = modal.querySelector('input, textarea, select');
            if (input) input.focus();
        }
    });

    // Confirmação em botões perigosos
    document.body.addEventListener('click', (e) => {
        if (e.target.matches('[data-confirm]') || e.target.closest('[data-confirm]')) {
            const msg = e.target.dataset.confirm || e.target.closest('[data-confirm]').dataset.confirm;
            if (!confirm(msg)) e.preventDefault();
        }
    });

    // Preview de imagem no upload
    document.body.addEventListener('change', (e) => {
        if (e.target.matches('input[type="file"][data-preview]')) {
            const file = e.target.files[0];
            const previewId = e.target.dataset.preview;
            const preview = document.getElementById(previewId);
            if (file && preview && file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (ev) => { preview.src = ev.target.result; preview.style.display = 'block'; };
                reader.readAsDataURL(file);
            }
        }
    });
});

// Utilitários globais
window.Helpdesk = {
    formatDuration: (seconds) => {
        if (!seconds) return '00:00:00';
        const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const s = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    },

    showToast: (message, type = 'info') => {
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };
        const toast = document.createElement('div');
        toast.className = `fixed bottom-4 right-4 ${colors[type]} text-white px-4 py-2 rounded shadow-lg animate-fade-in z-50`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }
};