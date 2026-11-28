# T Casino v2.3 (Telegram Mini App)

Telegram Mini App казино на 20 игр с серверным ГСЧ (`secrets`), PostgreSQL (Neon), приёмом Telegram Stars (`100 ⭐ = $1.00`), демо-режимом на $10 000 и админ-панелью.

## Структура проекта

- `main.py` — FastAPI бэкенд (20 игр, GZip-сжатие, кэширование статики, WebApp HMAC-SHA256 + `auth_date`, мульти-шарики в Плинко, корректный авто-кэшаут Краша, rate limiting, `/health`).
- `bot.py` — Telegram-бот на `aiogram 3` (Stars `XTR` с проверкой `PreCheckoutQuery`, заявки на вывод, `/users` с разбивкой по лимиту).
- `database.py` — пул `asyncpg` под Neon, `CHECK`-ограничения, индексы и журнал транзакций `transactions`.
- `static/index.html` — лёгкая разметка с мгновенным `tg.ready()` и `preload`.
- `static/styles.css` — стили, темы и анимации.
- `static/script.js` — логика 20 игр, 60 FPS мульти-шариковый Плинко, SFX на Web Audio API, поиск и избранное.
- `requirements.txt` — Python-зависимости.
- `start.sh` — скрипт запуска бота и `uvicorn`.
- `.env.example` — шаблон переменных окружения.

## Деплой на Render

1. Загрузите все файлы из архива в корень GitHub-репозитория, сохраняя папку `static/`.
2. Задайте переменные окружения в Render (обязательно `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_ID`, `WEBAPP_URL`).
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `bash start.sh` (или `python bot.py & uvicorn main:app --host 0.0.0.0 --port $PORT`).
5. Health Check Path: `/health`.
