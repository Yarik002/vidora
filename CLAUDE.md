# Vidora: правила проекта для ИИ-агентов

Vidora — учебная копия YouTube (тестовое задание). Код пишет ИИ, человек ставит задачи и проверяет.
Цель: на чистой Ubuntu одной командой (`./deploy.sh`) поднимается всё, и сразу работает сценарий
«регистрация → загрузка → просмотр → лайк и комментарий».

## Архитектура (коротко)
- `backend/` — модульный монолит на FastAPI. Слои: `api/` (роутеры, только HTTP) → `services/`
  (бизнес-логика, проверки прав) → `repositories/` (SQL-запросы). Модели SQLAlchemy 2 в `models/`,
  миграции Alembic в `backend/migrations/`.
- `backend/app/worker/` — воркер arq (Redis): ffprobe-проверка, транскод ffmpeg в H.264 MP4
  (faststart, 720p и 360p), превью, длительность. Статусы: uploading → uploaded → processing → ready | failed.
- Хранилище — MinIO (S3), бакеты приватные. Загрузка: браузер шлёт части напрямую в S3 по
  presigned-ссылкам (multipart) через `/storage/` на том же домене. Раздача: API проверяет права и
  отвечает 302 на короткоживущую presigned-ссылку (Range работает).
- `frontend/` — React + Vite + TypeScript, собирается в Docker, отдаётся Caddy.
- `deploy/caddy/Caddyfile` — reverse proxy: фронт, `/api`, `/docs`, `/storage`, TLS, заголовки безопасности.
- Подробно: `docs/architecture.md`, `docs/database.md`, `docs/security.md`, `docs/design-system.md`.

## Правила кода
- Python 3.12, типизация везде, async SQLAlchemy. Линтер: `ruff check` и `ruff format`.
- Роутер не ходит в БД напрямую: только через сервис. Проверка доступа к видео — одна функция
  `services/access.py`, её используют все ручки (просмотр, стрим, комментарии, реакции, поиск).
- Любое изменение схемы — новая миграция Alembic, старые миграции не правим.
- Ошибки наружу без деталей: 404 вместо 403 для приватных объектов (не раскрываем существование).
- Секреты только из переменных окружения (`.env` генерирует `scripts/gen_env.sh`). Никаких значений
  секретов в коде, логах, коммитах и в ответах агента.
- Фронт: только токены из `frontend/src/styles/tokens.css`, без «магических» цветов в компонентах.
  Логотип и бренд свои, брендинг YouTube не копируем.
- Тексты UI на русском.

## Как проверять (агент обязан делать это перед «готово»)
1. `docker compose up -d --build` — всё поднялось, `docker compose ps` без unhealthy.
2. Тесты: `docker compose -f compose.yml -f compose.test.yml run --rm tests`.
3. Линтер: `docker compose run --rm --no-deps api ruff check app tests`.
4. Сквозной сценарий: `python3 scripts/e2e.py` (по HTTPS через Caddy).
5. UI смотреть в браузере (https://localhost), а не верить коду на слово.
Если что-то не проверено — так и написать. Слово «работает» только после реального запуска.

## Git
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`, `refactor:`).
- Маленькие коммиты, ветка на этап (`feat/...`), merge `--no-ff` в `main`, тег на этап.
- Историю не переписываем, force push не делаем.
- Перед коммитом: `/precommit` (линтер, тесты, поиск секретов в diff).

## Окружение разработчика
Windows 11 + Docker Desktop. Node и ffmpeg локально нет: всё тяжёлое только в контейнерах.
Shell-скрипты с LF (см. `.gitattributes`), `.ps1` только латиницей.
