# Family Lab

Стартовая страница для d1ha.com.

Для локального запуска в PowerShell выполни `python server.py` и открой http://localhost:8000.

## Coolify

- Build Pack — Dockerfile
- Base Directory — /
- Dockerfile Location — /Dockerfile
- Domains — https://d1ha.com
- Ports Exposes — 8000
- Healthcheck — GET /healthz, ожидаемый статус 200
- Environment Variables — PORT=8000 (необязательно, это значение по умолчанию)
- База данных и volume не нужны. Поле Ports Mappings оставь пустым.
