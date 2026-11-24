FROM python:3.13-slim
WORKDIR /app
# ffmpeg/ffprobe: video validation and thumbnails
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "mediamind.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
