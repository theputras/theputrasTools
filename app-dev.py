from app import app

# Runner khusus development
# Jalankan file ini kalau mau ngoding di local: python app-dev.py
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)