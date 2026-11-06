FROM python:3.13.16-slim-trixie@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c
WORKDIR /app
ENV PORT=8000
COPY server.py index.html ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=4s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/healthz', timeout=2); raise SystemExit(r.status != 200)"]
CMD ["python", "-u", "server.py"]
