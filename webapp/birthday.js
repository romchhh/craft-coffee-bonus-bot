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

  let submitted = false;
  const card = document.querySelector(".date-card");
  const picker = window.CraftDateFields.mount(card);

  function send(payload) {
    const data = JSON.stringify(payload);
    if (tg?.sendData) {
      tg.sendData(data);
      return;
    }
    alert(data);
  }

  document.getElementById("confirm-btn").addEventListener("click", () => {
    if (submitted) return;
    const iso = picker.isoValue();
    if (!iso) {
      document.getElementById("preview").textContent = "Обери день, місяць і рік";
      return;
    }
    submitted = true;
    send({
      type: "birthday",
      birthday: iso,
      display: picker.displayValue(),
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
