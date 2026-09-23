FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OCR_LANG=ara+eng \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG SEGMENTATION_MODEL_URL=https://github.com/Malik05255/manzl_3D/releases/download/segmentation-v1/manzil-segmentation-v1.onnx
ARG SEGMENTATION_MODEL_SHA256=95963b8a3385809f640a4256d4953c29658612720156c5a081c6c3f84886929a
RUN mkdir -p /app/models && \
    python -c "import hashlib,urllib.request,pathlib; p=pathlib.Path('/app/models/manzil-segmentation-v1.onnx'); urllib.request.urlretrieve('$SEGMENTATION_MODEL_URL',p); h=hashlib.sha256(p.read_bytes()).hexdigest(); assert h=='$SEGMENTATION_MODEL_SHA256',(h,'$SEGMENTATION_MODEL_SHA256')"

COPY app ./app
ENV PORT=8080
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
