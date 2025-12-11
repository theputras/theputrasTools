document.addEventListener('alpine:init', () => {
    // --- 1. STORE UNTUK TOAST ---
    Alpine.store('toast', {
        items: [],
        show(type, message) {
            const id = Date.now();
            this.items.push({ id, type, message, show: true });
            setTimeout(() => this.remove(id), 3000); // Auto close 3 detik
        },
        remove(id) {
            const item = this.items.find(i => i.id === id);
            if (item) item.show = false;
            setTimeout(() => {
                this.items = this.items.filter(i => i.id !== id);
            }, 500);
        }
    });

    // --- 2. STORE UNTUK CONFIRMATION ---
    Alpine.store('confirm', {
        isOpen: false,
        title: '',
        message: '',
        type: 'danger', // 'danger' (merah) atau 'info' (biru)
        resolve: null,  // Fungsi untuk menyelesaikan Promise

        // Fungsi ini mengembalikan Promise, jadi bisa di-await
        ask(title, message, type = 'danger') {
            this.title = title;
            this.message = message;
            this.type = type;
            this.isOpen = true;

            return new Promise((resolve) => {
                this.resolve = resolve;
            });
        },

        close(result) {
            this.isOpen = false;
            if (this.resolve) {
                this.resolve(result); // true (Ya) atau false (Batal)
                this.resolve = null;
            }
        }
    });

    // --- GLOBAL HELPERS ---
    window.showAlert = (type, message) => Alpine.store('toast').show(type, message);
    window.showConfirm = (title, message, type) => Alpine.store('confirm').ask(title, message, type);
});