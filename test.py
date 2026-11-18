"""
Парсер проданих авто на AUTO.RIA (Київ + Київська область).

Публічний JSON API (без ключа developers.ria.com):

  GET https://auto.ria.com/api/search/search
      ?indexName=auto&category_id=1&state[0]=10&countpage=100&page=0&saledParam=1

  saledParam: 0=всі, 1=лише продані, 2=без проданих
  state[0]=10 — Київська обл. (Київ входить сюди ж)

Деталі:
  GET https://auto.ria.com/demo/bu/searchPage/v2/view/auto/{id}

Телефон (повний):
  GET https://auto.ria.com/demo/bu/mainPage/rotator/item/{id}?type=bu&langId=4
      → userSecure.hash
  GET https://auto.ria.com/users/phones/{id}?hash={hash}

Запуск:
    python test.py --today              # лише продані сьогодні + телефони
    python test.py --today --pages 5
    python test.py --pages 3
    python test.py --no-phone           # без запиту телефону
    python test.py --debug
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date, datetime

import requests

STATE_ID = 10  # Київська область (+ Київ)
CATEGORY_ID = 1
COUNTPAGE = 100

SEARCH_API = "https://auto.ria.com/api/search/search"
VIEW_API = "https://auto.ria.com/demo/bu/searchPage/v2/view/auto/{id}"
ROTATOR_API = "https://auto.ria.com/demo/bu/mainPage/rotator/item/{id}?type=bu&langId=4"
PHONES_API = "https://auto.ria.com/users/phones/{id}"

s = requests.Session()
s.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://auto.ria.com/uk/search/",
    "Origin": "https://auto.ria.com",
})


def log(*args, **kwargs):
    print(*args, file=sys.stderr, flush=True, **kwargs)


def pause(a=0.35, b=0.9):
    time.sleep(random.uniform(a, b))


def fetch_json(url, params=None, retries=3):
    last = None
    for attempt in range(retries):
        r = s.get(url, params=params, timeout=30)
        if r.status_code in (403, 429):
            wait = 2.5 * (attempt + 1)
            log(f"   {r.status_code} на {url.split('.com')[-1][:60]} — пауза {wait:.1f}s")
            time.sleep(wait)
            last = r
            continue
        if r.status_code >= 500 or not r.text.strip():
            time.sleep(1.2 * (attempt + 1))
            last = r
            continue
        r.raise_for_status()
        return r.json()
    if last is not None and last.status_code in (403, 429):
        raise RuntimeError(f"{last.status_code}: антибот/ліміт для {url}")
    raise RuntimeError(f"немає JSON від {url}")


def search_sold(page: int, state_id: int = STATE_ID) -> dict:
    params = {
        "indexName": "auto",
        "category_id": CATEGORY_ID,
        "state[0]": state_id,
        "countpage": COUNTPAGE,
        "page": page,
        "saledParam": 1,
    }
    return fetch_json(SEARCH_API, params)


def view_auto(auto_id: str) -> dict:
    return fetch_json(VIEW_API.format(id=auto_id))


def fetch_phones(auto_id: str) -> list[str]:
    """Повний номер через rotator hash → /users/phones."""
    try:
        rot = fetch_json(ROTATOR_API.format(id=auto_id))
    except Exception as e:
        log(f"   phone rotator {auto_id}: {e}")
        return []
    h = ((rot or {}).get("userSecure") or {}).get("hash")
    if not h:
        return []
    pause(0.25, 0.55)
    try:
        data = fetch_json(PHONES_API.format(id=auto_id), params={"hash": h})
    except Exception as e:
        log(f"   phone unlock {auto_id}: {e}")
        return []
    out = []
    for p in data.get("phones") or []:
        num = p.get("phoneFormatted") or p.get("phone")
        if num:
            out.append(num)
    if not out and data.get("formattedPhoneNumber"):
        out.append(data["formattedPhoneNumber"])
    return out


def ad_url(link_to_view: str | None, auto_id: str) -> str:
    if link_to_view:
        path = link_to_view if link_to_view.startswith("/") else "/" + link_to_view
        if not path.startswith("/uk/"):
            path = "/uk" + path
        return "https://auto.ria.com" + path
    return f"https://auto.ria.com/uk/auto_{auto_id}.html"


def sold_day(info: dict) -> str:
    return (info.get("soldDate") or "").strip()[:10]


def summarize_page(page: int, data: dict) -> dict:
    result = data.get("result") or {}
    sr = result.get("search_result") or {}
    add = result.get("additional") or {}
    cleaned = (add.get("search_params") or {}).get("cleaned") or {}
    ids = sr.get("ids") or []
    return {
        "page": page,
        "total_sold": sr.get("count"),
        "ids_on_page": len(ids),
        "first_ids": ids[:5],
        "query_string": add.get("query_string"),
        "cleaned_saledParam": cleaned.get("saledParam"),
        "cleaned_state": cleaned.get("state"),
    }


def format_ad_line(info: dict, auto_id: str, phones: list[str] | None = None) -> str:
    url = ad_url(info.get("linkToView"), auto_id)
    title = info.get("title") or "?"
    city = info.get("locationCityName") or "?"
    sold = info.get("soldDate") or "?"
    usd = info.get("USD")
    year = (info.get("autoData") or {}).get("year")
    race = (info.get("autoData") or {}).get("race")
    price = f"${usd}" if usd is not None else "?"
    bits = [url, title, price]
    if year:
        bits.append(str(year))
    if race:
        bits.append(str(race))
    bits.append(city)
    bits.append(f"продано {sold}")
    if phones:
        bits.append("тел: " + ", ".join(phones))
    else:
        masked = ((info.get("userPhoneData") or {}).get("phone")) or ""
        if masked:
            bits.append(f"тел: {masked} (маски)")
        else:
            bits.append("тел: —")
    return " | ".join(bits)


def main():
    ap = argparse.ArgumentParser(description="Продані авто AUTO.RIA (Київщина) через JSON API")
    ap.add_argument("--pages", type=int, default=4, help="сторінок пошуку (по 100 id)")
    ap.add_argument("--limit", type=int, default=0, help="стоп після N виведених (0=без ліміту)")
    ap.add_argument("--today", action="store_true", help="лише soldDate = сьогодні")
    ap.add_argument("--day", type=str, default="", help="фільтр YYYY-MM-DD (замість --today)")
    ap.add_argument("--no-phone", action="store_true", help="не розкривати телефон")
    ap.add_argument("--no-details", action="store_true", help="лише id, без view")
    ap.add_argument("--debug", action="store_true", help="зберегти JSON 1-ї сторінки")
    ap.add_argument("--state", type=int, default=STATE_ID, help="state id області (10=Київська)")
    args = ap.parse_args()

    day_filter = args.day.strip() or (date.today().isoformat() if args.today else "")

    log(f"API: {SEARCH_API}")
    log(f"фільтр: category_id={CATEGORY_ID} state[0]={args.state} saledParam=1 countpage={COUNTPAGE}")
    if day_filter:
        log(f"день soldDate: {day_filter}")

    if args.debug:
        data = search_sold(0, args.state)
        path = "debug_search.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        meta = summarize_page(0, data)
        log("meta:", json.dumps(meta, ensure_ascii=False))
        log(f"Збережено {path}")
        return

    checked = printed = skipped_day = 0
    today_count = 0
    seen = set()
    total_hint = None
    day_counts: dict[str, int] = {}

    for page in range(args.pages):
        t0 = time.time()
        try:
            data = search_sold(page, args.state)
        except Exception as e:
            log(f"-- сторінка {page}: ПОМИЛКА запиту: {e}")
            break

        meta = summarize_page(page, data)
        total_hint = meta["total_sold"]
        ids = (data.get("result") or {}).get("search_result", {}).get("ids") or []
        elapsed = time.time() - t0

        log(
            f"-- сторінка {page}: ids={meta['ids_on_page']}, "
            f"total_sold≈{meta['total_sold']}, "
            f"saledParam={meta['cleaned_saledParam']}, "
            f"state={meta['cleaned_state']}, "
            f"{elapsed:.2f}s"
        )
        log(f"   query: {meta['query_string']}")
        log(f"   sample ids: {meta['first_ids']}")

        if not ids:
            log("   порожня видача — кінець")
            break

        page_new = page_printed = 0
        for auto_id in ids:
            if auto_id in seen:
                continue
            seen.add(auto_id)
            checked += 1
            page_new += 1

            if args.no_details:
                print(f"id={auto_id} https://auto.ria.com/uk/search/?auto_id_str={auto_id}", flush=True)
                printed += 1
                page_printed += 1
                if args.limit and printed >= args.limit:
                    break
                continue

            try:
                pause()
                info = view_auto(auto_id)
            except Exception as e:
                log(f"   view {auto_id}: {e}")
                continue

            sd = sold_day(info)
            if sd:
                day_counts[sd] = day_counts.get(sd, 0) + 1
            if sd == date.today().isoformat():
                today_count += 1

            if day_filter and sd != day_filter:
                skipped_day += 1
                continue

            phones: list[str] = []
            if not args.no_phone:
                pause(0.2, 0.5)
                phones = fetch_phones(auto_id)

            printed += 1
            page_printed += 1
            print(format_ad_line(info, auto_id, phones), flush=True)

            if args.limit and printed >= args.limit:
                break

        log(
            f"   підсумок сторінки: нових={page_new}, виведено={page_printed}, "
            f"пропущено(день)={skipped_day}, сьогодні(накопичено scan)={today_count}, "
            f"всього виведено={printed}"
        )
        if args.limit and printed >= args.limit:
            log(f"   досягнуто --limit {args.limit}")
            break
        pause(0.8, 1.6)

    log(f"\nГотово. Перевірено id: {checked}, виведено: {printed}, total_sold≈{total_hint}")
    log(f"Продано сьогодні ({date.today().isoformat()}) серед просканованих: {today_count}")
    if day_counts:
        top_days = sorted(day_counts.items(), reverse=True)[:7]
        log("по днях (scan): " + ", ".join(f"{d}={c}" for d, c in top_days))
    if day_filter:
        log(f"фільтр дня {day_filter}: виведено {printed}, відсіяно {skipped_day}")
    if checked == 0:
        log("Нічого не знайдено. Спробуй --debug.")


if __name__ == "__main__":
    main()
