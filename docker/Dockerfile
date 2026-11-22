FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn pydantic numpy Pillow onnxruntime python-multipart

COPY src/ src/
COPY artifacts/student.onnx artifacts/student.onnx
COPY configs/ configs/

EXPOSE 8000
ENV PYTHONPATH=/app/src AP_MODE=onnx AP_MODEL_PATH=artifacts/student.onnx AP_HOST=0.0.0.0 AP_PORT=8000
CMD ["python", "-m", "uvicorn", "aesthetic_prism.serve.app:app", "--host", "0.0.0.0", "--port", "8000"]
