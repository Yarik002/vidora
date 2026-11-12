---
description: Проверка перед коммитом - линтер, тесты, поиск секретов в diff
---

Выполни проверку перед коммитом и коротко отчитайся (что прошло, что нет):

1. `git status --short` и `git diff --cached --stat` — что именно уходит в коммит.
2. Поиск секретов в staged diff: `git diff --cached | grep -nEi "(password|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}"`
   и проверка, что `.env` и `TZ.docx` не попали в индекс. Значения найденного не печатай, только файл и строку.
3. Линтер бэкенда: `docker compose run --rm --no-deps api ruff check app tests`.
4. Если менялся бэкенд — тесты: `docker compose -f compose.yml -f compose.test.yml run --rm tests`.
5. Если менялся фронт — сборка: `docker compose build web`.
6. Сообщение коммита в стиле Conventional Commits, одна логическая правка на коммит.

Если что-то упало — не коммить, сначала исправь или сообщи.
