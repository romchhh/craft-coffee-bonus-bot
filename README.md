# Craft Coffee — Telegram loyalty bot

Telegram-бот і Mini App для програми лояльності **Craft Coffee**: реєстрація, картка зі штрихкодом, бонуси, кешбек (Заряд), меню з Poster, адмін-панель.

## Стек

- Python 3.11+, [aiogram](https://docs.aiogram.dev/) 3
- aiohttp (Mini App + API + Poster webhook)
- SQLite, Poster POS API

## Швидкий старт

1. Скопіюй `.env.example` → `.env` і заповни `TOKEN`, `POSTER_TOKEN`, `WEBAPP_URL` (HTTPS).
2. `pip install -r requirements.txt`
3. `python main.py`

Mini App: `WEBAPP_URL` (наприклад ngrok). У BotFather — Web App на цей URL.  
Poster webhook: `{WEBAPP_URL}/webhook/poster`

## Корисні команди

```bash
# Перевірка пропущених чеків (dry-run)
python -m services.loyalty_cron --dry-run --days 7

# Нарахування пропущених чеків
python -m services.loyalty_cron --apply --days 7
```

## Структура

- `main.py` — бот + веб-сервер
- `handlers/` — клієнт і адмін
- `webapp/` — Mini App (HTML/JS/CSS)
- `services/` — Poster, лояльність, крон чеків

Секрети та локальна БД (`database/data.db`) у git не потрапляють.
