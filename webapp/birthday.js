(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#ffffff");
      tg.setBackgroundColor("#ffffff");
      if (typeof tg.disableVerticalSwipes === "function") {
        tg.disableVerticalSwipes();
      }
    } catch (_) {}
  }

  const input = document.getElementById("birthday-input");
  const preview = document.getElementById("preview");
  const confirmBtn = document.getElementById("confirm-btn");
  let submitted = false;

  function bounds() {
    const now = new Date();
    const max = new Date(now.getFullYear() - 10, now.getMonth(), now.getDate());
    const min = new Date(now.getFullYear() - 90, now.getMonth(), now.getDate());
    const toIso = (d) => {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}-${m}-${day}`;
    };
    return { min: toIso(min), max: toIso(max) };
  }

  function displayFromIso(iso) {
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return "ДД.ММ.РРРР";
    return `${m[3]}.${m[2]}.${m[1]}`;
  }

  function syncUi() {
    const iso = (input.value || "").trim();
    const label = iso ? displayFromIso(iso) : "ДД.ММ.РРРР";
    preview.textContent = label;
    confirmBtn.disabled = !iso || submitted;
  }

  function send(payload) {
    const data = JSON.stringify(payload);
    if (tg?.sendData) {
      tg.sendData(data);
      return;
    }
    alert(data);
  }

  function openPickerFromGesture() {
    if (submitted) return;
    try {
      if (typeof input.showPicker === "function") {
        input.showPicker();
        return;
      }
    } catch (_) {}
    input.focus({ preventScroll: true });
  }

  const { min, max } = bounds();
  input.min = min;
  input.max = max;
  syncUi();

  preview.addEventListener("click", openPickerFromGesture);

  input.addEventListener("input", syncUi);
  input.addEventListener("change", syncUi);

  confirmBtn.addEventListener("click", () => {
    if (submitted) return;
    const iso = (input.value || "").trim();
    if (!iso) {
      preview.textContent = "Спочатку обери дату";
      openPickerFromGesture();
      return;
    }
    submitted = true;
    confirmBtn.disabled = true;
    send({
      type: "birthday",
      birthday: iso,
      display: displayFromIso(iso),
    });
  });

  document.getElementById("skip-btn").addEventListener("click", () => {
    if (submitted) return;
    submitted = true;
    send({ type: "birthday", skip: true });
  });

  if (window.lucide?.createIcons) {
    window.lucide.createIcons({ attrs: { "stroke-width": 2.2 } });
  }
})();
