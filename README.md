# Craft Coffee — Telegram loyalty system

Telegram-бот + Mini App для програми лояльності **Craft Coffee** (мережа кав’ярень):
реєстрація, цифрова картка зі штрихкодом, бонуси, кешбек (Заряд), квести, реферали,
меню та історія покупок через Poster POS.

---

## Технічна характеристика системи

| Параметр | Значення |
|---|---|
| Тип системи | Telegram Bot + Telegram Mini App + HTTP API |
| Мова | Python 3.11+ |
| Бот-фреймворк | aiogram 3.x (long polling) |
| HTTP | aiohttp (Mini App static + JSON API + Poster webhook) |
| БД | SQLite (один файл `database/data.db`, WAL) |
| POS / CRM | Poster API (`joinposter.com`) |
| Часовий пояс | `Europe/Kyiv` для всієї клієнтської логіки |
| Курс бонусів | 1 бонус = 1 грн |
| Деплой | один процес: бот + веб на `WEBAPP_HOST:WEBAPP_PORT` |
| Секрети | `.env` (не в git); приклад — `.env.example` |

### Модулі продукту

1. **Реєстрація** — ім’я + телефон → клієнт Poster + EAN-13 картка + вітальні 50 грн.
2. **Mini App** — штрихкод, баланс, Заряд/рівень кешбеку, квести, точки, меню, історія.
3. **Кешбек (Заряд)** — після закритого чека; % залежить від рівня; списання бонусів до 50% чека (Poster).
4. **Квести / досягнення** — 3 візити, напій+їжа, 2 напої; перша покупка; дні 5/15/30. Суми в адмінці.
5. **Реферали** — запрошення після власної першої покупки; другу 50 при реєстрації (+20 за ДН); запрошувачу 10 після покупки друга ≥50 грн грошима, доступно з наступної 00:00 Києва; ліміт 5/день авто, далі черга адміна; clawback при поверненні.
6. **Адмінка** — статистика, розсилка, посилання, адміни, налаштування винагород, реферали на перевірці.
7. **Інтеграції** — Poster webhook + фоновий cron закритих чеків; опційно Apple Wallet `.pkpass`.

### Потік даних (чеки → бонуси)

```
Poster (каса) → webhook /webhook/poster  ─┐
                                          ├─→ process_closed_transaction
Loyalty cron (кожні N сек) ───────────────┘
        → кешбек % + quests + реферал (кваліфікація)
        → changeClientBonus у Poster
        → повідомлення в Telegram
Referral grants (після 00:00 Києва) → нарахування запрошувачу
```

### API Mini App (коротко)

| Метод | Шлях | Призначення |
|---|---|---|
| GET | `/` | Mini App UI |
| GET | `/api/meta` | публічні метадані |
| GET | `/api/me` | картка, баланс, Заряд, квести |
| POST | `/api/me/birthday` | дата народження + бонус профілю |
| GET | `/api/spots` | точки мережі |
| GET | `/api/menu` | меню Poster (відфільтроване) |
| GET | `/api/history` | історія покупок |
| GET | `/api/wallet/*` | Apple Wallet (якщо налаштовано) |
| POST | `/webhook/poster` | webhook Poster |

Авторизація Mini App: Telegram WebApp `initData` (HMAC).

### Сховище (SQLite)

- `users` — клієнти бота, картка, реферер, Заряд
- `settings` — суми винагород, % кешбеку
- `processed_transactions` — ідемпотентність чеків
- `quest_progress` / `quest_event_log` — квести
- `referrals` — реферальний цикл і статуси
- адміни, посилання, службові таблиці

### Обмеження / залежності

- Потрібен **HTTPS** `WEBAPP_URL` (Telegram Mini App + webhook).
- Баланс бонусів — джерело істини в **Poster**; локальна БД тримає стан програми.
- Окремі «лоти» строку бонусів 30 днів у Poster не ведуться повною книгою партій; реферальні `expires_at` зберігаються для обліку.
- `KRAFT_LOYALTY/` — архів продуктових рішень / прототипів, не runtime.

---

## Швидкий старт

1. Скопіюй `.env.example` → `.env`, заповни `TOKEN`, `POSTER_TOKEN`, `WEBAPP_URL`, `ADMINISTRATORS`.
2. `pip install -r requirements.txt`
3. `python main.py` або `./start_bot.sh start`

У BotFather вкажи Web App URL = `WEBAPP_URL`.  
У Poster: webhook `{WEBAPP_URL}/webhook/poster` (entities: `transaction`, `client_payed_sum`).

### Операційні команди

```bash
./start_bot.sh start|restart|stop

# Пропущені чеки
python -m services.loyalty_cron --dry-run --days 7
python -m services.loyalty_cron --apply --days 7

# Poster tooling (не для продакшену)
python scripts/poster_tool.py
python scripts/test_order.py --list-spots
```

---

## Структура репозиторію

```
main.py                 # точка входу: polling + web
config.py               # env-конфіг
webapp_server.py        # Mini App + API + webhook
handlers/               # aiogram routers (client / admin)
services/               # Poster, loyalty, quests, referrals, wallet
database_functions/     # SQLite schema + access
webapp/                 # static Mini App
Content/                # тексти бота, локації
keyboards/ states/ utils/
scripts/                # ops / Poster test tools
KRAFT_LOYALTY/          # product decisions archive (optional)
```

Секрети, `database/data.db`, `cache/`, `logs/*.log`, сертифікати Wallet у git не зберігаються.
