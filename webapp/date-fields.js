(() => {
  const MONTHS = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
  ];

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function daysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
  }

  function defaultBounds() {
    const now = new Date();
    const maxYear = now.getFullYear() - 10;
    const minYear = now.getFullYear() - 90;
    return { minYear, maxYear, defaultYear: 1995, defaultMonth: 6, defaultDay: 15 };
  }

  function fillSelect(el, items, placeholder) {
    el.innerHTML = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = placeholder;
    el.appendChild(ph);
    for (const it of items) {
      const opt = document.createElement("option");
      if (typeof it === "object") {
        opt.value = String(it.value);
        opt.textContent = it.label;
      } else {
        opt.value = String(it);
        opt.textContent = String(it);
      }
      el.appendChild(opt);
    }
  }

  function mount(root, options = {}) {
    const bounds = { ...defaultBounds(), ...options };
    const dayEl = root.querySelector("[data-bd-day], #bd-day");
    const monthEl = root.querySelector("[data-bd-month], #bd-month");
    const yearEl = root.querySelector("[data-bd-year], #bd-year");
    const previewEl = root.querySelector("[data-bd-preview], #preview, .bd-preview");

    if (!dayEl || !monthEl || !yearEl) {
      throw new Error("date-fields: missing select elements");
    }

    const years = [];
    for (let y = bounds.maxYear; y >= bounds.minYear; y -= 1) {
      years.push(y);
    }
    fillSelect(yearEl, years, "Рік");
    fillSelect(
      monthEl,
      MONTHS.map((label, i) => ({ value: i + 1, label })),
      "Місяць",
    );

    function refreshDays() {
      const y = Number(yearEl.value);
      const m = Number(monthEl.value);
      const prev = Number(dayEl.value);
      let maxDay = 31;
      if (y && m) maxDay = daysInMonth(y, m);
      const days = [];
      for (let d = 1; d <= maxDay; d += 1) days.push(d);
      fillSelect(dayEl, days, "День");
      if (prev && prev <= maxDay) dayEl.value = String(prev);
    }

    function isoValue() {
      const y = Number(yearEl.value);
      const m = Number(monthEl.value);
      const d = Number(dayEl.value);
      if (!y || !m || !d) return "";
      if (d > daysInMonth(y, m)) return "";
      return `${y}-${pad2(m)}-${pad2(d)}`;
    }

    function displayValue() {
      const iso = isoValue();
      if (!iso) return "ДД.ММ.РРРР";
      const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!m) return "ДД.ММ.РРРР";
      return `${m[3]}.${m[2]}.${m[1]}`;
    }

    function syncPreview() {
      if (previewEl) previewEl.textContent = displayValue();
    }

    function onAnyChange() {
      refreshDays();
      syncPreview();
      if (typeof options.onChange === "function") {
        options.onChange(isoValue(), displayValue());
      }
    }

    yearEl.addEventListener("change", onAnyChange);
    monthEl.addEventListener("change", onAnyChange);
    dayEl.addEventListener("change", onAnyChange);

    yearEl.value = String(bounds.defaultYear);
    monthEl.value = String(bounds.defaultMonth);
    refreshDays();
    dayEl.value = String(bounds.defaultDay);
    syncPreview();

    return {
      isoValue,
      displayValue,
      syncPreview,
      setIso(iso) {
        const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!m) return;
        yearEl.value = m[1];
        monthEl.value = String(Number(m[2]));
        refreshDays();
        dayEl.value = String(Number(m[3]));
        syncPreview();
      },
      elements: { dayEl, monthEl, yearEl },
    };
  }

  window.CraftDateFields = { mount, defaultBounds, displayFromIso: (iso) => {
    const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return "ДД.ММ.РРРР";
    return `${m[3]}.${m[2]}.${m[1]}`;
  } };
})();
