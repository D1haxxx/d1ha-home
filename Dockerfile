FROM python:3.13.16-slim-trixie@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c
WORKDIR /app
ENV HOST=0.0.0.0 PORT=8000 PUBLIC_ORIGIN=https://d1ha.com DATA_DIR=/data PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.11.0+cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && install -d -o 10001 -g 10001 /data
COPY *.py *.json *.pt ./
COPY website/dist/ website/dist/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=4s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/healthz', timeout=2).close()"]
CMD ["python", "web.py"]
