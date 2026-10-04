(() => {
  const tg = window.Telegram?.WebApp;

  function isMobileWebApp() {
    const p = String(tg?.platform || "").toLowerCase();
    if (p === "ios" || p === "android") return true;
    if (p === "tdesktop" || p === "macos" || p === "web" || p === "weba") return false;
    if (typeof window.matchMedia === "function") {
      return window.matchMedia("(max-width: 519px)").matches;
    }
    return true;
  }

  function syncViewportMode() {
    const mobile = isMobileWebApp();
    document.documentElement.classList.toggle("app-mobile", mobile);
    document.documentElement.classList.toggle("app-desktop", !mobile);
    return mobile;
  }

  function applyTelegramChrome() {
    if (!tg) {
      syncViewportMode();
      return;
    }
    const mobile = syncViewportMode();
    try {
      tg.setHeaderColor("#ffffff");
      tg.setBackgroundColor("#ffffff");
      if (typeof tg.disableVerticalSwipes === "function") {
        tg.disableVerticalSwipes();
      }
      if (mobile) {
        if (typeof tg.requestFullscreen === "function") {
          tg.requestFullscreen();
        }
        if (typeof tg.expand === "function") {
          tg.expand();
        }
      }
    } catch (_) {}
  }

  if (tg) {
    tg.ready();
    applyTelegramChrome();
  }

  const content = document.getElementById("content");
  const tabs = document.getElementById("tabs");

  function setTabsVisible(show) {
    if (!tabs) return;
    tabs.classList.toggle("tabs-hidden", !show);
    if (show) tabs.removeAttribute("hidden");
    else tabs.setAttribute("hidden", "");
  }
  let state = {
    tab: "card",
    me: null,
    spots: null,
    menu: null,
    menuCategories: null,
    menuError: null,
    history: null,
  };
  const barcodeModal = document.getElementById("barcode-modal");
  const barcodeModalSvg = document.getElementById("barcode-modal-svg");
  const barcodeModalBackdrop = document.getElementById("barcode-modal-backdrop");
  const barcodeModalClose = document.getElementById("barcode-modal-close");
  const barcodeModalNumber = document.getElementById("barcode-modal-number");
  let menuScrollHandler = null;
  let menuNavLock = false;
  let menuNavLockTimer = null;
  let appReady = false;
  let menuLoading = false;
  let appMeta = null;
  let lastVisibilityReload = 0;

  async function getAppMeta() {
    if (appMeta) return appMeta;
    try {
      const res = await fetch("/api/meta");
      appMeta = await res.json();
    } catch (_) {
      appMeta = {};
    }
    return appMeta;
  }

  function openBotUrl(url) {
    if (!url) return;
    try {
      if (tg?.openTelegramLink) tg.openTelegramLink(url);
      else if (tg?.openLink) tg.openLink(url);
      else window.open(url, "_blank", "noopener");
    } catch (_) {
      window.location.href = url;
    }
  }

  function bindBotLinkButton() {
    const btn = document.getElementById("open-bot-link");
    if (!btn) return;
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      openBotUrl(btn.getAttribute("data-bot-url") || btn.href);
    });
  }

  async function showLoadError({ kind, message }) {
    const meta = await getAppMeta();
    const botUrl = meta.start_url || meta.bot_url || "";
    const needsBot = kind === "session" || kind === "register" || kind === "auth";

    let title = "Щось пішло не так";
    let hint = "Спробуй ще раз або звернись у підтримку в боті.";
    let botLabel = "Відкрити бота Craft Coffee";

    if (kind === "session") {
      title = "Не вдалося увійти";
      hint = "Картку можна відкрити лише з Telegram — через кнопку «Картка» в боті, а не в браузері.";
      botLabel = "Перейти до бота";
    } else if (kind === "register") {
      title = "Картка ще не оформлена";
      hint = "Спочатку зареєструйся в боті — це займе хвилину.";
      botLabel = "Зареєструватися в боті";
    } else if (kind === "auth") {
      title = "Сесію не вдалося перевірити";
      hint = "Закрий мініап і відкрий знову з кнопки «Картка» в боті.";
      botLabel = "Відкрити бота";
    }

    const botBlock = needsBot && botUrl
      ? `<a href="${escapeHtml(botUrl)}" class="btn-bot-link" id="open-bot-link" data-bot-url="${escapeHtml(botUrl)}">${escapeHtml(botLabel)}</a>`
      : "";

    content.innerHTML = `<div class="empty">
      <div class="empty-ico">${icon("shield-alert")}</div>
      <p><strong>${escapeHtml(title)}</strong></p>
      <div class="error">${escapeHtml(message)}</div>
      <p class="muted">${escapeHtml(hint)}</p>
      ${botBlock}
      <button type="button" class="btn-retry" id="app-retry-btn">Спробувати знову</button>
    </div>`;
    paintIcons();
    bindBotLinkButton();
    const retryBtn = document.getElementById("app-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        resetInitDataCache();
        loadAll();
      });
    }
  }

  const fmtMoney = (n) => {
    const v = Number(n || 0);
    return v.toLocaleString("uk-UA", { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + " грн";
  };

  const hasBirthday = (raw) => Boolean(raw && raw !== "0000-00-00");

  const fmtBirthday = (raw) => {
    if (!hasBirthday(raw)) return "не вказано";
    const m = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) return `${m[3]}.${m[2]}.${m[1]}`;
    const dmy = String(raw).match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
    if (dmy) return `${dmy[1]}.${dmy[2]}.${dmy[3]}`;
    return String(raw);
  };

  const cardIdHtml = (cardNumber) => {
    const digits = String(cardNumber || "").replace(/\D/g, "");
    if (!digits) return "";
    if (digits.length < 4) {
      return `<div class="card-id-line">${escapeHtml(digits)}</div>`;
    }
    const head = digits.slice(0, -4);
    const tail = digits.slice(-4);
    return `<div class="card-id-line" aria-label="Номер картки">
      <span class="card-id-head">${escapeHtml(head)}</span>
      <span class="card-id-tail" aria-label="Останні 4 цифри">${escapeHtml(tail)}</span>
      <span class="card-id-label">id</span>
    </div>
    <p class="muted card-id-hint">Назви ці 4 цифри на касі, якщо не сканується штрихкод</p>`;
  };

  const fmtDateTime = (raw) => {
    if (!raw || raw === "—") return "—";
    const m = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (!m) return String(raw);
    const base = `${m[3]}.${m[2]}.${m[1]}`;
    if (m[4] != null) return `${base}, ${m[4]}:${m[5]}`;
    return base;
  };

  const escapeHtml = (s) => String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  const icon = (name) => `<i data-lucide="${name}"></i>`;

  const catIcon = (cat = "") => {
    const c = cat.toLowerCase();
    if (/кав|кофе|coffee|еспрес|латте|капуч|американо|раф/.test(c)) return "coffee";
    if (/чай|tea/.test(c)) return "cup-soda";
    if (/десерт|торт|тістеч|печив|солод/.test(c)) return "cake";
    if (/снідан|яєц|тост|омлет/.test(c)) return "egg";
    if (/смузі|фреш|сік|лимонад|напій/.test(c)) return "glass-water";
    if (/їжа|салат|суп|сендвіч|бургер/.test(c)) return "utensils-crossed";
    return "sparkles";
  };

  function paintIcons(root) {
    if (!window.lucide?.createIcons) return;
    const opts = { attrs: { "stroke-width": 2.2 } };
    if (root) {
      window.lucide.createIcons({ ...opts, root });
    } else {
      window.lucide.createIcons(opts);
    }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let cachedInitData = null;
  let initDataPromise = null;

  function readInitDataFromHash() {
    const hash = (window.location.hash || "").replace(/^#/, "").trim();
    if (!hash) return "";
    if (hash.includes("hash=")) return hash;
    try {
      const params = new URLSearchParams(hash);
      const tgData = params.get("tgWebAppData");
      if (tgData) {
        const decoded = decodeURIComponent(tgData);
        if (decoded.includes("hash=")) return decoded;
      }
    } catch (_) {}
    return "";
  }

  function readInitDataRaw() {
    if (tg) {
      const direct = (tg.initData || "").trim();
      if (direct && direct.includes("hash=")) return direct;
    }
    const fromHash = readInitDataFromHash();
    if (fromHash) return fromHash;
    try {
      const params = new URLSearchParams(window.location.search || "");
      const fromQuery = (params.get("tgWebAppData") || params.get("initData") || "").trim();
      if (fromQuery && fromQuery.includes("hash=")) return fromQuery;
    } catch (_) {}
    return tg ? (tg.initData || "").trim() : "";
  }

  function buildApiHeaders(initData) {
    const headers = { "ngrok-skip-browser-warning": "1" };
    if (initData) headers["X-Telegram-Init-Data"] = initData;
    return headers;
  }

  function resetInitDataCache() {
    cachedInitData = null;
    initDataPromise = null;
  }

  async function resolveInitData(force = false) {
    if (!tg) return "";
    if (!force && cachedInitData) return cachedInitData;
    if (!force && initDataPromise) return initDataPromise;

    initDataPromise = (async () => {
      tg.ready();
      if (isMobileWebApp()) {
        try {
          tg.expand();
        } catch (_) {}
      }
      for (let i = 0; i < 320; i++) {
        const raw = readInitDataRaw();
        if (raw && raw.includes("hash=")) {
          cachedInitData = raw;
          return raw;
        }
        await sleep(40);
      }
      const fallback = readInitDataRaw();
      if (fallback) cachedInitData = fallback;
      return fallback;
    })();

    try {
      return await initDataPromise;
    } finally {
      if (!cachedInitData) initDataPromise = null;
    }
  }

  async function api(path, attempt = 0) {
    const maxAttempts = 5;
    const initData = await resolveInitData(attempt > 0);
    const res = await fetch(`/api${path}`, { headers: buildApiHeaders(initData) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const errText = data.error || `HTTP ${res.status}`;
      if (res.status === 401 && attempt < maxAttempts - 1) {
        resetInitDataCache();
        await sleep(180 + attempt * 220);
        return api(path, attempt + 1);
      }
      if (res.status === 404 && /me/.test(path) && attempt < maxAttempts - 1) {
        await sleep(400 + attempt * 350);
        return api(path, attempt + 1);
      }
      const err = new Error(errText);
      err.httpStatus = res.status;
      throw err;
    }
    return data;
  }

  async function apiPost(path, body, attempt = 0) {
    const maxAttempts = 5;
    const initData = await resolveInitData(attempt > 0);
    const headers = { ...buildApiHeaders(initData), "Content-Type": "application/json" };
    const res = await fetch(`/api${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401 && attempt < maxAttempts - 1) {
        resetInitDataCache();
        await sleep(180 + attempt * 220);
        return apiPost(path, body, attempt + 1);
      }
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  function cssEscape(value) {
    const s = String(value);
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
      return CSS.escape(s);
    }
    return s.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function lockAppScroll() {
    document.body.classList.add("barcode-modal-open");
    content.classList.add("scroll-locked");
  }

  function unlockAppScroll() {
    document.body.classList.remove("barcode-modal-open");
    content.classList.remove("scroll-locked");
  }

  function closeBarcodeModal() {
    if (!barcodeModal || barcodeModal.hidden) return;
    barcodeModal.hidden = true;
    barcodeModal.setAttribute("aria-hidden", "true");
    unlockAppScroll();
  }

  function openBarcodeModal(code) {
    if (!code || !barcodeModal || !barcodeModalSvg) return;
    paintBarcodeInto(barcodeModalSvg, code, true);
    if (barcodeModalNumber) {
      barcodeModalNumber.innerHTML = cardIdHtml(code);
    }
    barcodeModal.hidden = false;
    barcodeModal.setAttribute("aria-hidden", "false");
    lockAppScroll();
    barcodeModalClose?.focus();
  }

  function paintBarcodeInto(el, code, large) {
    if (!el || !window.JsBarcode || !code) return;
    const format = code.length === 13 ? "EAN13" : "CODE128";
    const opts = {
      format,
      displayValue: false,
      margin: large ? 8 : 6,
      height: large ? 220 : 72,
      width: large ? 2.8 : 2,
      background: "#ffffff",
      lineColor: "#111111",
    };
    try {
      JsBarcode(el, code, opts);
    } catch (_) {
      JsBarcode(el, code, { ...opts, format: "CODE128" });
    }
    if (large) {
      el.style.width = "100%";
      el.style.height = "auto";
      el.setAttribute("preserveAspectRatio", "xMidYMid meet");
    }
  }

  function setTab(tab) {
    state.tab = tab;
    closeBarcodeModal();
    unlockAppScroll();
    [...tabs.querySelectorAll("button")].forEach((b) => {
      b.setAttribute("aria-current", b.dataset.tab === tab ? "page" : "false");
    });
    if (!appReady) return;
    if (tab === "menu" && (!state.menu || state.menu.length === 0) && !menuLoading) {
      loadMenu();
      return;
    }
    render();
    content.scrollTop = 0;
  }

  function paintBarcode(code) {
    const el = document.getElementById("card-barcode");
    paintBarcodeInto(el, code, false);
  }

  function renderLoyaltyCharge(me) {
    const L = me.loyalty;
    if (!L) return "";
    const bonus = Number(me.bonus || 0);
    const pct = L.cashback_percent ?? 5;
    const next = L.next_percent ?? pct;
    const charge = Number(L.charge ?? 0);
    const goal = Number(L.charge_goal ?? 50);
    const rem = Number(L.charge_remaining ?? Math.max(0, goal - charge));
    const progress = goal > 0 ? Math.min(100, (charge / goal) * 100) : 0;
    const atMax = pct >= (L.max_tier ?? 10);
    const levels = (L.levels || [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
      .map((n) => `<span class="level-pill${n === pct ? " on" : ""}">${n}%</span>`)
      .join("");
    const bonusLine = L.bonus_hint
      ? `<p class="loyalty-warn">До ${escapeHtml(L.bonus_hint.date)} використай <strong>${escapeHtml(String(L.bonus_hint.amount))} грн</strong> бонусів — інакше вони згорять після ${L.bonus_hint.days_without_purchase} днів без покупок.</p>`
      : "";

    const mapsUrl = escapeHtml(L.maps_url || "https://www.google.com/maps");
    const bonusBanner = bonus > 0
      ? `<button type="button" class="loyalty-use-banner" data-maps-url="${mapsUrl}">
          <span class="loyalty-use-banner-ico">${icon("gift")}</span>
          <span class="loyalty-use-banner-text">
            <strong>${L.bonus_hint
              ? `До ${escapeHtml(L.bonus_hint.date)} використай ${escapeHtml(String(L.bonus_hint.amount))} грн бонусів`
              : `На балансі ${escapeHtml(String(Math.floor(bonus * 100) / 100))} грн — час скористатися`}</strong>
            <span class="muted">Маршрут до Craft Coffee в Google Maps</span>
          </span>
          <span class="loyalty-use-banner-arrow" aria-hidden="true">${icon("arrow-up-right")}</span>
        </button>`
      : "";

    return `
      <div class="panel loyalty-panel">
        <div class="loyalty-head">
          <div>
            <div class="loyalty-kicker">Кешбек</div>
            <div class="loyalty-percent">${pct}<span>%</span></div>
          </div>
          ${atMax ? `<div class="loyalty-badge">${icon("zap")} Макс. рівень</div>` : `
          <div class="loyalty-next">
            <div class="muted">До ${next}% — ще ${rem % 1 === 0 ? rem : rem.toFixed(1)} Заряду</div>
            <div class="charge-meta"><span>${icon("zap")}</span> ${charge % 1 === 0 ? charge : charge.toFixed(1)} / ${goal}</div>
          </div>`}
        </div>
        ${atMax ? "" : `<div class="charge-track" aria-hidden="true"><div class="charge-fill" style="width:${progress}%"></div></div>`}
        ${bonusBanner}
        <details class="loyalty-details">
          <summary>Як це працює ${icon("chevron-down")}</summary>
          <div class="loyalty-details-body">
            <h4>Рівні кешбеку</h4>
            <div class="level-row">${levels}</div>
            <h4>Як отримати Заряд</h4>
            <p class="muted">Перша зарахована покупка дня: 50–150 грн — <strong>1 Заряд</strong>, понад 150 грн — <strong>2</strong>. Наступні того ж дня: <strong>0,5</strong> або <strong>1,5</strong>. Між зарахованими візитами — не менше 2 годин.</p>
            <h4>Що відбувається під час перерви</h4>
            <p class="muted">Після 30 календарних днів без покупок незавершений Заряд зменшується на 0,5 за день до нуля. Бонуси згорають, якщо 90 днів не було покупок.</p>
            ${bonusLine}
          </div>
        </details>
      </div>`;
  }

  function renderBarcode(code) {
    return `<div class="barcode-wrap" id="barcode-btn" role="button" tabindex="0" aria-label="Збільшити штрихкод">
      <svg id="card-barcode" aria-hidden="true"></svg>
    </div>`;
  }

  function renderCard() {
    const me = state.me;
    if (!me) {
      return `<div class="empty">
        <div class="empty-ico">${icon("credit-card")}</div>
        <p><strong>Картку не знайдено</strong></p>
        <p class="muted">Заверши реєстрацію в боті командою /start</p>
      </div>`;
    }
    const code = me.card_number || "";
    const Q = me.quests || {};
    const refBonus = Q.referral_bonus_uah ?? 10;
    const initial = (me.name || "?").trim().charAt(0).toUpperCase();
    const avatar = me.photo_url
      ? `<img class="avatar" src="${escapeHtml(me.photo_url)}" alt="" width="48" height="48">`
      : `<div class="avatar avatar-fallback" aria-hidden="true">${escapeHtml(initial)}</div>`;
    return `
      <div class="panel panel-hero">
        ${code ? renderBarcode(code) : `<div class="empty"><p class="muted">Номер картки ще не сформовано</p></div>`}
        ${code ? `<div class="tap-hint">
          ${icon("maximize-2")}
          Натисни, щоб збільшити штрихкод
        </div>
        ${cardIdHtml(code)}
        <div class="card-holder">
          ${avatar}
          <div class="card-holder-body">
            <div class="card-holder-name">${escapeHtml(me.name)}</div>
          </div>
        </div>` : `
        <div class="card-holder">
          ${avatar}
          <div class="card-holder-body">
            <div class="card-holder-name">${escapeHtml(me.name)}</div>
          </div>
        </div>`}
      </div>

      <div class="panel panel-balance">
        <div class="balance-label">${icon("gift")} Доступні бонуси</div>
        <div class="big">${fmtMoney(me.bonus)}</div>
        <div class="balance-note">1 бонус = 1 грн · покажи код на касі</div>
      </div>

      ${renderLoyaltyCharge(me)}

      <button type="button" class="referral-hero" id="open-referral-quest">
        <span class="referral-hero-ico">${icon("users")}</span>
        <span>
          <strong>Приведи друга — ${escapeHtml(String(refBonus))} грн</strong>
          <span class="muted">Поділись посиланням у розділі «Квести»</span>
        </span>
      </button>
    `;
  }

  function renderQuests() {
    const me = state.me;
    if (!me) return renderCard();
    const Q = me.quests || {};
    const bBonus = Q.birthday_bonus_uah ?? 10;
    const rBonus = Q.referral_bonus_uah ?? 10;
    const bDone = Boolean(Q.birthday_bonus_claimed);
    const refLink = Q.referral_link || "";
    const refCount = Number(Q.referrals_count ?? 0);
    const doneBadge = `<span class="quest-status">${icon("check")} Виконано</span>`;
    const bdayDisplay = hasBirthday(me.birthday) ? fmtBirthday(me.birthday) : "";

    let html = `<div class="section-title"><div class="title-ico">${icon("sparkles")}</div><h2>Квести</h2></div>
      <p class="muted" style="margin-top:-6px">Виконуй завдання — отримуй бонуси на картку</p>`;

    const activeParts = [];
    const doneParts = [];

    if (!bDone) {
      activeParts.push(`
      <div class="quest-card">
        <div class="quest-reward">${icon("cake")} +${escapeHtml(String(bBonus))} грн</div>
        <h3>Поділись датою народження</h3>
        <p class="muted">Вкажи день народження — нарахуємо бонуси одразу.</p>
        <div class="birthday-profile-picker" id="profile-birthday-root">
          <div class="birthday-picker-preview" data-bd-preview>ДД.ММ.РРРР</div>
          <div class="date-fields">
            <label class="date-field"><span>День</span><select data-bd-day></select></label>
            <label class="date-field"><span>Місяць</span><select data-bd-month></select></label>
            <label class="date-field"><span>Рік</span><select data-bd-year></select></label>
          </div>
          <div class="quest-actions">
            <button type="button" class="btn-quest" id="save-birthday-btn">Зберегти та отримати бонус</button>
          </div>
        </div>
        <p class="birthday-add-error hidden" id="birthday-error" role="alert"></p>
      </div>`);
    } else {
      doneParts.push(`
      <div class="quest-card done">
        <div class="quest-card-head">
          <h3>Поділись датою народження</h3>
          ${doneBadge}
        </div>
        <div class="quest-reward">${icon("cake")} +${escapeHtml(String(bBonus))} грн</div>
        <p class="muted">Бонус нараховано на картку.${bdayDisplay ? ` Дата: <strong>${escapeHtml(bdayDisplay)}</strong>.` : ""}</p>
      </div>`);
    }

    activeParts.push(`
      <div class="quest-card">
        <div class="quest-reward">${icon("users")} +${escapeHtml(String(rBonus))} грн за друга</div>
        <h3>Приведи друга</h3>
        <p class="muted">Надішли посилання. Коли друг оформить картку — отримаєш бонуси.${refCount ? ` Вже запрошено: <strong>${refCount}</strong>.` : ""}</p>
        <div class="quest-actions">
          <button type="button" class="btn-quest" id="copy-referral-link" ${refLink ? "" : "disabled"}>Скопіювати</button>
          <button type="button" class="btn-quest secondary" id="share-referral-link" ${refLink ? "" : "disabled"}>Поділитись</button>
        </div>
      </div>`);

    if (refCount > 0) {
      const totalRef = refCount * rBonus;
      doneParts.push(`
      <div class="quest-card done">
        <div class="quest-card-head">
          <h3>Друзі за твоїм посиланням</h3>
          ${doneBadge}
        </div>
        <div class="quest-reward">${icon("users")} +${escapeHtml(String(totalRef))} грн</div>
        <p class="muted">Оформили картку: <strong>${refCount}</strong> · по <strong>${escapeHtml(String(rBonus))} грн</strong> за кожного</p>
      </div>`);
    }

    if (activeParts.length) {
      html += `<div class="quest-section-title">Активні</div>${activeParts.join("")}`;
    }
    if (doneParts.length) {
      html += `<div class="quest-section-title">Виконані</div>${doneParts.join("")}`;
    }
    if (!activeParts.length && !doneParts.length) {
      html += `<div class="empty"><p class="muted">Квести скоро з’являться</p></div>`;
    }

    return html;
  }

  function renderSpots() {
    const spots = state.spots || [];
    const ig = state.spotsInstagram || appMeta?.instagram_url || "";
    let html = `<div class="section-title"><div class="title-ico">${icon("map-pin")}</div><h2>Наші точки</h2></div>`;
    if (ig) {
      html += `<a class="spots-instagram" href="${escapeHtml(ig)}" target="_blank" rel="noopener">
        ${icon("instagram")} Шукай нас в Instagram
      </a>`;
    }
    if (!spots.length) {
      return html + `<div class="empty"><div class="empty-ico">${icon("map")}</div><p class="muted">Адреси скоро з’являться</p></div>`;
    }
    html += spots.map((s, i) => {
      const maps = s.maps_url ? ` data-maps-url="${escapeHtml(s.maps_url)}"` : "";
      const photo = s.photo_url ? escapeHtml(s.photo_url) : "";
      const tag = s.maps_url ? "button" : "div";
      return `
      <${tag} type="button" class="spot-card-photo spot-card-action" style="animation-delay:${i * 0.05}s"${maps}>
        ${photo ? `<img src="${photo}" alt="" loading="lazy" decoding="async">` : ""}
        <div class="spot-card-photo-body">
          <h3>${escapeHtml(s.name)}</h3>
          <div class="muted">${escapeHtml(s.address || "—")}</div>
          ${s.maps_url ? `<span class="spot-open-map">${icon("navigation")} Маршрут до цієї кавʼярні</span>` : ""}
        </div>
      </${tag}>`;
    }).join("");
    return html;
  }

  function menuCatDomId(key) {
    return `menu-cat-${String(key).replace(/[^a-zA-Z0-9_-]/g, "_")}`;
  }

  function renderMenu() {
    const items = state.menu || [];
    const catsMeta = state.menuCategories || [];
    let html = `<div class="menu-page">
      <div class="menu-page-head">
        <div class="section-title"><div class="title-ico">${icon("utensils")}</div><h2>Меню</h2></div>
        <p class="muted menu-sub">Ціни з Poster · ${items.length} позицій</p>
      </div>`;
    if (menuLoading) {
      return html + `<div class="loader menu-loader"><div class="loader-icon">${icon("utensils")}</div><p>Завантажуємо меню з Poster…</p></div></div>`;
    }
    if (!items.length) {
      const err = state.menuError
        ? `<p class="error" style="margin-top:12px">${escapeHtml(state.menuError)}</p>`
        : `<p class="muted">Не вдалося отримати позиції з Poster</p>`;
      return html + `<div class="empty">
        <div class="empty-ico">${icon("coffee")}</div>
        ${err}
        <button type="button" class="menu-retry-btn" id="menu-retry-btn">${icon("refresh-cw")} Оновити меню</button>
      </div></div>`;
    }
    const byCat = {};
    for (const p of items) {
      const key = p.category_id || p.category || "Інше";
      (byCat[key] ||= { name: p.category || "Інше", items: [] }).items.push(p);
    }
    const catOrder = catsMeta.length
      ? catsMeta.map((c) => c.id)
      : Object.keys(byCat);
    const catPhoto = Object.fromEntries(
      catsMeta.filter((c) => c.photo_url).map((c) => [c.id, c.photo_url])
    );
    const orderedKeys = [
      ...catOrder.filter((k) => byCat[k]),
      ...Object.keys(byCat).filter((k) => !catOrder.includes(k)),
    ];

    html += `<div class="menu-cat-nav" id="menu-cat-nav" role="tablist" aria-label="Категорії меню">`;
    for (const key of orderedKeys) {
      const block = byCat[key];
      if (!block) continue;
      html += `<button type="button" class="menu-cat-chip" role="tab" data-cat-jump="${escapeHtml(key)}" aria-selected="false">${escapeHtml(block.name)}</button>`;
    }
    html += `</div><div class="menu-sections">`;

    let delay = 0;
    for (const key of orderedKeys) {
      const block = byCat[key];
      if (!block) continue;
      const catName = block.name;
      const list = block.items;
      const catImg = catPhoto[key];
      const catVisual = catImg
        ? `<img class="cat-photo" src="${escapeHtml(catImg)}" alt="" loading="lazy" width="40" height="40">`
        : `<div class="cat-ico">${icon(catIcon(catName))}</div>`;
      const sectionId = menuCatDomId(key);
      html += `<section class="menu-card" id="${sectionId}" data-cat-section="${escapeHtml(key)}" style="animation-delay:${delay}s">
        <div class="cat-head">
          ${catVisual}
          <h3>${escapeHtml(catName)}</h3>
        </div>`;
      for (const p of list.slice(0, 80)) {
        const thumb = p.photo_url
          ? `<img class="menu-thumb" src="${escapeHtml(p.photo_url)}" alt="" loading="lazy" width="52" height="52">`
          : `<div class="menu-thumb menu-thumb-fallback">${icon("coffee")}</div>`;
        html += `<div class="menu-row">
          ${thumb}
          <span class="name">${escapeHtml(p.name)}</span>
          <span class="price">${p.price != null ? fmtMoney(p.price) : "—"}</span>
        </div>`;
      }
      html += `</section>`;
      delay += 0.05;
    }
    html += `</div></div>`;
    return html;
  }

  function menuNavHeight() {
    const nav = document.getElementById("menu-cat-nav");
    return (nav?.offsetHeight || 48) + 6;
  }

  function sectionScrollTop(sec) {
    const cr = content.getBoundingClientRect();
    const sr = sec.getBoundingClientRect();
    return content.scrollTop + (sr.top - cr.top);
  }

  function setMenuCatActive(catKey, scrollChipIntoView = false) {
    const nav = document.getElementById("menu-cat-nav");
    if (!nav || catKey == null) return;
    const key = String(catKey);
    nav.querySelectorAll("[data-cat-jump]").forEach((btn) => {
      const on = btn.dataset.catJump === key;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (!scrollChipIntoView) return;
    const activeBtn = nav.querySelector(`[data-cat-jump="${cssEscape(key)}"]`);
    if (activeBtn) {
      activeBtn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
  }

  function updateMenuCatFromScroll(sections) {
    if (menuNavLock || !sections.length) return;
    const anchor = content.scrollTop + menuNavHeight() + 10;
    let current = sections[0].dataset.catSection;
    for (const sec of sections) {
      if (sectionScrollTop(sec) <= anchor) {
        current = sec.dataset.catSection;
      }
    }
    setMenuCatActive(current, true);
  }

  function teardownMenuCategoryNav() {
    if (menuScrollHandler) {
      content.removeEventListener("scroll", menuScrollHandler);
      menuScrollHandler = null;
    }
    if (menuNavLockTimer) {
      clearTimeout(menuNavLockTimer);
      menuNavLockTimer = null;
    }
    menuNavLock = false;
  }

  function setupMenuCategoryNav() {
    teardownMenuCategoryNav();
    const nav = document.getElementById("menu-cat-nav");
    if (!nav) return;

    const sections = [...content.querySelectorAll("[data-cat-section]")];
    if (!sections.length) return;

    const jumpTo = (key) => {
      const el = document.getElementById(menuCatDomId(key));
      if (!el) return;
      menuNavLock = true;
      clearTimeout(menuNavLockTimer);
      setMenuCatActive(key, true);
      const top = Math.max(0, sectionScrollTop(el) - menuNavHeight());
      content.scrollTo({ top, behavior: "smooth" });
      menuNavLockTimer = setTimeout(() => {
        menuNavLock = false;
        updateMenuCatFromScroll(sections);
      }, 450);
    };

    nav.querySelectorAll("[data-cat-jump]").forEach((btn) => {
      btn.addEventListener("click", () => jumpTo(btn.dataset.catJump));
    });

    const navH = nav.offsetHeight;
    document.documentElement.style.setProperty("--menu-nav-h", `${navH}px`);

    setMenuCatActive(sections[0].dataset.catSection, false);

    let scrollRaf = 0;
    menuScrollHandler = () => {
      if (scrollRaf) return;
      scrollRaf = requestAnimationFrame(() => {
        scrollRaf = 0;
        updateMenuCatFromScroll(sections);
      });
    };
    content.addEventListener("scroll", menuScrollHandler, { passive: true });
    updateMenuCatFromScroll(sections);
  }

  function historySortKey(raw) {
    const m = String(raw || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (!m) return "00000000000000";
    return `${m[1]}${m[2]}${m[3]}${m[4] || "00"}${m[5] || "00"}${m[6] || "00"}`;
  }

  function buildHistoryTimeline(hist) {
    const rows = [];
    for (const p of hist.purchases || []) {
      rows.push({ kind: "purchase", date: p.date, purchase: p });
    }
    for (const b of hist.bonuses || []) {
      rows.push({ kind: "bonus", date: b.date, bonus: b });
    }
    rows.sort((a, b) => historySortKey(b.date).localeCompare(historySortKey(a.date)));
    return rows;
  }

  function renderHistory() {
    const hist = state.history || { purchases: [], bonuses: [] };
    let html = `<div class="section-title"><div class="title-ico">${icon("history")}</div><h2>Історія</h2></div>
      <p class="muted" style="margin-top:-6px">Покупки та бонуси в одному списку</p>`;

    const blocks = [];
    for (const row of buildHistoryTimeline(hist)) {
      if (row.kind === "purchase") {
        const p = row.purchase;
        const cashback = Number(p.cashback_uah || 0);
        const spent = Number(p.bonus_spent || 0);
        let extra = "";
        if (cashback > 0) {
          extra += `<div class="hist-extra plus">+${fmtMoney(cashback)} кешбек</div>`;
        }
        if (spent > 0) {
          extra += `<div class="hist-extra minus">−${fmtMoney(spent)} бонусів</div>`;
        }
        blocks.push(`
          <div class="hist-card">
            <div class="ico">${icon("shopping-bag")}</div>
            <div style="flex:1;min-width:0">
              <div class="muted">${escapeHtml(fmtDateTime(p.date))} · ${escapeHtml(p.spot || "Craft Coffee")}</div>
              <h3>Покупка · ${fmtMoney(p.sum)}</h3>
              <div class="muted" style="margin-top:4px">Сплачено ${fmtMoney(p.payed)}</div>
              ${extra}
            </div>
          </div>`);
      } else {
        const b = row.bonus;
        const positive = Number(b.amount) >= 0;
        blocks.push(`
          <div class="hist-card">
            <div class="ico">${icon(positive ? "gift" : "banknote")}</div>
            <div style="flex:1;min-width:0">
              <div class="muted">${escapeHtml(fmtDateTime(b.date))}</div>
              <h3>${escapeHtml(b.title)}</h3>
            </div>
            <span class="price ${positive ? "plus" : "minus"}">${positive ? "+" : ""}${fmtMoney(b.amount)}</span>
          </div>`);
      }
    }
    if (!blocks.length) {
      html += `<div class="empty">
        <div class="empty-ico">${icon("sprout")}</div>
        <p><strong>Поки тихо</strong></p>
        <p class="muted">Зроби першу покупку з карткою — і історія з’явиться тут</p>
      </div>`;
    } else {
      html += blocks.join("");
    }
    return html;
  }

  function render() {
    closeBarcodeModal();
    let html = "";
    try {
      if (state.tab === "card") html = renderCard();
      else if (state.tab === "quests") html = renderQuests();
      else if (state.tab === "spots") html = renderSpots();
      else if (state.tab === "menu") html = renderMenu();
      else if (state.tab === "history") html = renderHistory();
    } catch (err) {
      console.error("render", state.tab, err);
      html = `<div class="empty">
        <div class="empty-ico">${icon("alert-circle")}</div>
        <p><strong>Не вдалося показати розділ</strong></p>
        <p class="muted">${escapeHtml(err.message || String(err))}</p>
      </div>`;
    }
    content.innerHTML = html;
    paintIcons();

    if (state.tab === "menu") {
      try {
        setupMenuCategoryNav();
      } catch (err) {
        console.error("menu nav", err);
      }
      const retry = document.getElementById("menu-retry-btn");
      if (retry) retry.addEventListener("click", () => loadMenu(true));
    } else {
      teardownMenuCategoryNav();
    }

    if (state.tab === "card" && state.me?.card_number) {
      requestAnimationFrame(() => paintBarcode(state.me.card_number));
    }
    const barcode = document.getElementById("barcode-btn");
    if (barcode) {
      const open = (e) => {
        e.preventDefault();
        openBarcodeModal(state.me?.card_number);
      };
      barcode.addEventListener("click", open);
      barcode.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") open(e);
      });
    }
    const openExternal = (url) => {
      if (!url) return;
      try {
        if (tg?.openLink) tg.openLink(url);
        else window.open(url, "_blank", "noopener");
      } catch (_) {
        window.location.href = url;
      }
    };

    content.querySelectorAll("[data-maps-url]").forEach((btn) => {
      btn.addEventListener("click", () => openExternal(btn.getAttribute("data-maps-url")));
    });

    content.querySelectorAll(".spots-instagram").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        openExternal(link.getAttribute("href"));
      });
    });

    const openReferral = document.getElementById("open-referral-quest");
    if (openReferral) {
      openReferral.addEventListener("click", () => setTab("quests"));
    }

    const birthdayRoot = document.getElementById("profile-birthday-root");
    const saveBirthdayBtn = document.getElementById("save-birthday-btn");
    const birthdayError = document.getElementById("birthday-error");
    if (birthdayRoot && saveBirthdayBtn && window.CraftDateFields) {
      const picker = window.CraftDateFields.mount(birthdayRoot);
      saveBirthdayBtn.addEventListener("click", async () => {
        const iso = picker.isoValue();
        if (!iso) {
          if (birthdayError) {
            birthdayError.textContent = "Обери день, місяць і рік";
            birthdayError.classList.remove("hidden");
          }
          return;
        }
        saveBirthdayBtn.disabled = true;
        if (birthdayError) birthdayError.classList.add("hidden");
        try {
          const res = await apiPost("/me/birthday", { birthday: iso });
          if (state.me) {
            state.me.birthday = res.birthday;
            if (res.quests) state.me.quests = res.quests;
            if (res.bonus_added) {
              state.me.bonus = Number(state.me.bonus || 0) + Number(res.bonus_added);
            }
          }
          render();
        } catch (err) {
          saveBirthdayBtn.disabled = false;
          if (birthdayError) {
            birthdayError.textContent = err.message || "Не вдалося зберегти";
            birthdayError.classList.remove("hidden");
          }
        }
      });
    }

    const refLink = state.me?.quests?.referral_link || "";
    const copyRef = document.getElementById("copy-referral-link");
    if (copyRef && refLink) {
      copyRef.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(refLink);
          copyRef.textContent = "Скопійовано ✓";
          setTimeout(() => { copyRef.textContent = "Скопіювати посилання"; }, 2000);
        } catch (_) {
          window.prompt("Скопіюй посилання:", refLink);
        }
      });
    }
    const shareRef = document.getElementById("share-referral-link");
    if (shareRef && refLink) {
      shareRef.addEventListener("click", () => {
        const text = "Оформи картку Craft Coffee — бонуси за каву ☕";
        if (navigator.share) {
          navigator.share({ title: "Craft Coffee", text, url: refLink }).catch(() => {});
        } else if (tg?.openTelegramLink) {
          tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(refLink)}&text=${encodeURIComponent(text)}`);
        } else {
          openExternal(refLink);
        }
      });
    }
  }

  async function loadMenu(force = false) {
    if (menuLoading && !force) return;
    menuLoading = true;
    state.menuError = null;
    if (state.tab === "menu") render();
    try {
      const menu = await api(force ? "/menu?refresh=1" : "/menu");
      if (!menu || !Array.isArray(menu.items)) {
        throw new Error("Некоректна відповідь сервера (меню)");
      }
      state.menu = menu.items;
      state.menuCategories = menu.categories || [];
      if (!state.menu.length) {
        state.menuError = menu.error || "Poster повернув порожнє меню";
      }
    } catch (e) {
      state.menuError = e.message || "Помилка завантаження меню";
      if (!state.menu) state.menu = [];
    } finally {
      menuLoading = false;
      if (appReady) render();
    }
  }

  async function loadSecondaryData() {
    try {
      const [spots, history] = await Promise.all([api("/spots"), api("/history")]);
      state.spots = spots.items || [];
      state.spotsInstagram = spots.instagram_url || "";
      state.history = history;
      if (state.tab === "spots" || state.tab === "history" || state.tab === "quests") render();
    } catch (e) {
      console.warn("secondary load", e);
      if (!state.spots) state.spots = [];
      if (!state.history) state.history = { purchases: [], bonuses: [] };
    }
  }

  function setLoaderMessage(text) {
    const p = content.querySelector(".loader p");
    if (p) p.textContent = text;
  }

  function isRetriableLoadError(e) {
    const msg = String(e.message || "");
    if (e.code === "session" || /сесію Telegram/i.test(msg)) return true;
    if (/Не зареєстровано/i.test(msg)) return true;
    if (/перевірити сесію|401/i.test(msg)) return true;
    if (e.httpStatus === 401 || e.httpStatus === 404) return true;
    return false;
  }

  async function loadAll(attempt = 0) {
    const maxAttempts = 6;
    if (attempt === 0) {
      appReady = false;
      setTabsVisible(false);
      tabs.setAttribute("aria-busy", "true");
      content.innerHTML = `<div class="loader"><div class="loader-icon">${icon("coffee")}</div><p>Завантаження…</p></div>`;
      paintIcons();
    } else {
      setLoaderMessage(`З’єднуємо картку… (${attempt + 1}/${maxAttempts})`);
    }
    try {
      const initData = await resolveInitData(attempt > 0);
      if (tg && !initData) {
        const err = new Error("Не вдалося отримати сесію Telegram.");
        err.code = "session";
        throw err;
      }
      const me = await api("/me");
      state.me = me;
      state.spots = [];
      state.history = { purchases: [], bonuses: [] };
      appReady = true;
      tabs.removeAttribute("aria-busy");
      setTabsVisible(true);
      try {
        if (typeof tg?.enableClosingConfirmation === "function") {
          tg.enableClosingConfirmation();
        }
      } catch (_) {}
      render();
      loadSecondaryData();
      loadMenu();
    } catch (e) {
      if (isRetriableLoadError(e) && attempt < maxAttempts - 1) {
        resetInitDataCache();
        await sleep(300 + attempt * 280);
        return loadAll(attempt + 1);
      }
      appReady = true;
      tabs.removeAttribute("aria-busy");
      setTabsVisible(false);
      const msg = String(e.message || "");
      let kind = "generic";
      if (e.code === "session" || /сесію Telegram/i.test(msg)) kind = "session";
      else if (/Не зареєстровано/i.test(msg)) kind = "register";
      else if (/перевірити сесію|401/i.test(msg)) kind = "auth";
      await showLoadError({ kind, message: msg });
    }
  }

  tabs.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    setTab(btn.dataset.tab);
  });

  if (barcodeModalBackdrop) {
    barcodeModalBackdrop.addEventListener("click", closeBarcodeModal);
  }
  if (barcodeModalClose) {
    barcodeModalClose.addEventListener("click", closeBarcodeModal);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && barcodeModal && !barcodeModal.hidden) {
      closeBarcodeModal();
    }
  });

  paintIcons(tabs);
  paintIcons();
  async function boot() {
    if (tg) {
      tg.ready();
      applyTelegramChrome();
      await sleep(80);
      applyTelegramChrome();
    }
    await loadAll();
  }

  if (tg) {
    const kickInit = () => {
      resetInitDataCache();
      resolveInitData(true).then((raw) => {
        if (raw && raw.includes("hash=") && !state.me && appReady) {
          loadAll();
        }
      });
    };
    try {
      tg.onEvent("viewportChanged", () => {
        applyTelegramChrome();
        kickInit();
      });
      tg.onEvent("themeChanged", kickInit);
      tg.onEvent("webAppReady", kickInit);
    } catch (_) {}
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastVisibilityReload < 2500) return;
      lastVisibilityReload = now;
      resetInitDataCache();
      if (!state.me) loadAll();
    });
  }
  boot();
})();
