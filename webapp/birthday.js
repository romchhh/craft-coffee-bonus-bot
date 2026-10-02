(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#ffffff");
      tg.setBackgroundColor("#ffffff");
      tg.enableClosingConfirmation();
      if (typeof tg.disableVerticalSwipes === "function") {
        tg.disableVerticalSwipes();
      }
    } catch (_) {}
  }

  const MONTHS = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
  ];

  const input = document.getElementById("birthday-input");
  const preview = document.getElementById("preview");

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
    return { min: toIso(min), max: toIso(max), defaultValue: "1995-06-15" };
  }

  function displayFromIso(iso) {
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return "—";
    const day = Number(m[3]);
    const month = Number(m[2]) - 1;
    const year = m[1];
    return `${String(day).padStart(2, "0")}.${String(month + 1).padStart(2, "0")}.${year} · ${day} ${MONTHS[month]} ${year}`;
  }

  function updatePreview() {
    preview.textContent = input.value ? displayFromIso(input.value) : "—";
  }

  function send(payload) {
    const data = JSON.stringify(payload);
    if (tg?.sendData) {
      tg.sendData(data);
      return;
    }
    alert(data);
  }

  const { min, max, defaultValue } = bounds();
  input.min = min;
  input.max = max;
  input.value = defaultValue;
  updatePreview();

  input.addEventListener("input", updatePreview);
  input.addEventListener("change", updatePreview);

  document.getElementById("confirm-btn").addEventListener("click", () => {
    const iso = (input.value || "").trim();
    if (!iso) {
      preview.textContent = "Обери дату в календарі";
      input.focus();
      return;
    }
    send({
      type: "birthday",
      birthday: iso,
      display: displayFromIso(iso).split(" · ")[0],
    });
  });

  document.getElementById("skip-btn").addEventListener("click", () => {
    send({ type: "birthday", birthday: null, skip: true });
  });

  if (window.lucide?.createIcons) {
    window.lucide.createIcons({ attrs: { "stroke-width": 2.2 } });
  }
})();
