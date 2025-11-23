# Gunakan image Python resmi dari Docker Hub
FROM python:3.12-slim

# Setel direktori kerja di dalam container
WORKDIR /app

# Salin konten direktori lokal ke dalam container di /app
COPY . /app

# Update pip dan install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Ekspose port 5000
EXPOSE 5000
# Tentukan variabel lingkungan
ENV FLASK_APP=app.py                                                                                                                                                                                             
ENV FLASK_RUN_HOST=0.0.0.0   

# Kunci timezone                                                                                                                                                                                                 
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Jakarta


# Jalankan aplikasi Flask menggunakan Gunicorn untuk produksi
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "1", "-k", "gthread", "--threads", "8", "app:app"]