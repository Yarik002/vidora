---
description: Поднять стек и прогнать сквозной сценарий регистрация - загрузка - просмотр - лайк и комментарий
---

1. `docker compose up -d --build` и дождись, пока `docker compose ps` покажет все сервисы healthy.
2. Запусти `python3 scripts/e2e.py --base https://localhost` (на Windows: `py -3.11 scripts/e2e.py`).
3. Если упало — посмотри `docker compose logs --tail=100 api worker caddy`, найди причину
   (не гадай), исправь, повтори. Отчитайся: какие шаги прошли, сколько заняла обработка видео.
