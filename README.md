# D1ha AI

Веб-интерфейс D1ha и Python-сервер с моделями, работающими на CPU.

## Coolify

- Build Pack — Dockerfile, Base Directory — /, Dockerfile Location — /Dockerfile.
- Domains — https://d1ha.com. Ports Exposes — 8000. Ports Mappings — пусто.
- Environment Variables — PUBLIC_ORIGIN=https://d1ha.com.
- Healthcheck встроен в Dockerfile и проверяет GET /healthz.
- Для сохранения отзывов и событий между деплоями добавь именованный volume на /data. Отдельный PostgreSQL для этого приложения не используется.
- Google-вход и Brave Search необязательны. Гостевой чат работает без них.
