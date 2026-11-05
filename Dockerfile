FROM python:3.13.16-slim-trixie@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c
WORKDIR /app
ENV PORT=8000
COPY server.py index.html ./
USER 10001:10001
EXPOSE 8000
CMD ["python", "-u", "server.py"]
