/** Legal copy for Mini App: loyalty rules + privacy policy (Ukrainian). */
(function (global) {
  "use strict";

  const UPDATED = "12.10.2026";

  function rulesHtml() {
    return `
      <div class="legal-page">
        <button type="button" class="legal-back" data-legal-back>
          ← На головну
        </button>
        <div class="section-title">
          <div class="title-ico"><i data-lucide="book-open"></i></div>
          <h2>Правила програми</h2>
        </div>
        <p class="muted legal-updated">Оновлено ${UPDATED} · Craft Coffee (Бровари)</p>

        <div class="panel legal-panel">
          <h3>1. Що це за програма</h3>
          <p>Цифрова картка лояльності Craft Coffee у Telegram-боті та мінізастосунку. На балансі — <strong>бонуси</strong>: <strong>1 бонус на касі = 1 грн</strong>.</p>
        </div>

        <div class="panel legal-panel">
          <h3>2. Картка та штрихкод</h3>
          <ul class="legal-list">
            <li>Після реєстрації створюється клієнт у касовій системі Poster і номер бонусної картки.</li>
            <li>На касі покажи <strong>штрихкод</strong> у мініапі (або назви останні 4 цифри під ним, якщо сканер не зчитав).</li>
            <li>Без картки нарахування й списання з балансу Craft Coffee не працюють.</li>
          </ul>
        </div>

        <div class="panel legal-panel">
          <h3>3. Нарахування на баланс</h3>
          <ul class="legal-list">
            <li><strong>Вітальний бонус</strong> — після оформлення картки (сума з налаштувань програми, зазвичай 50).</li>
            <li><strong>Кешбек</strong> — відсоток від суми покупки (оплаченої грошима) після закриття чека на касі. Поточний % залежить від рівня Заряду (див. нижче).</li>
            <li><strong>День народження</strong> — одноразова винагорода за вказану дату в мініапі; можливий щорічний подарунок у день народження (якщо увімкнено).</li>
            <li><strong>Приведи друга</strong> — див. розділ 6.</li>
          </ul>
          <p class="muted">Джерело балансу — касова система Poster. У мініапі показується актуальний залишок після синхронізації.</p>
        </div>

        <div class="panel legal-panel">
          <h3>4. Списання з балансу</h3>
          <ul class="legal-list">
            <li>Списання робить бариста на касі після сканування твоєї картки.</li>
            <li>Скільки саме можна списати з одного чека — за правилами каси Poster (часто є ліміт частки чека).</li>
            <li>Баланс не обмінюється на готівку і не переказується іншій людині.</li>
          </ul>
        </div>

        <div class="panel legal-panel">
          <h3>5. Заряд і рівні кешбеку</h3>
          <p>Стартовий кешбек — <strong>1%</strong>. Рівень зростає накопичувально за <strong>Заряди</strong>.</p>
          <ul class="legal-list">
            <li><strong>1 Заряд</strong> = один закритий чек на суму від <strong>50 грн</strong> (оплата грошима).</li>
            <li>Немає обмеження «раз на 2 години» чи «один заряд на день» — кожен чек ≥50 грн дає 1 Заряд.</li>
          </ul>
          <p><strong>Скільки Зарядів потрібно накопичити, щоб досягти рівня:</strong></p>
          <div class="legal-table" role="table">
            <div class="legal-tr" role="row"><span>1%</span><span>0 (старт)</span></div>
            <div class="legal-tr" role="row"><span>2%</span><span>15</span></div>
            <div class="legal-tr" role="row"><span>3%</span><span>25</span></div>
            <div class="legal-tr" role="row"><span>4%</span><span>50</span></div>
            <div class="legal-tr" role="row"><span>5%</span><span>100</span></div>
            <div class="legal-tr" role="row"><span>6%</span><span>200</span></div>
            <div class="legal-tr" role="row"><span>7%</span><span>400</span></div>
            <div class="legal-tr" role="row"><span>8%</span><span>800</span></div>
            <div class="legal-tr" role="row"><span>9%</span><span>1600</span></div>
            <div class="legal-tr" role="row"><span>10%</span><span>3000</span></div>
          </div>
          <p class="muted">Чим вищий рівень — тим більше Зарядів потрібно для наступного. У мініапі в блоці кешбеку показано лише <em>наступний</em> крок.</p>
          <h4>Пауза в покупках</h4>
          <ul class="legal-list">
            <li>Після <strong>30 днів</strong> без покупок незавершений прогрес до наступного рівня може зменшуватися (0,5 Заряду за день), але вже досягнутий поріг рівня не «скидається» нижче поточного порогу.</li>
            <li>Якщо <strong>90 днів</strong> не було покупок — залишок бонусів на балансі може згоріти (про це є нагадування в мініапі, коли є баланс).</li>
          </ul>
        </div>

        <div class="panel legal-panel">
          <h3>6. Приведи друга</h3>
          <ol class="legal-list">
            <li>Поділись своїм запрошувальним посиланням (доступне одразу після реєстрації).</li>
            <li>Друг реєструється за цим посиланням у боті.</li>
            <li>Друг робить покупку від <strong>50 грн</strong> грошима (протягом відведеного вікна, зазвичай 30 днів).</li>
            <li>Тобі нараховується винагорода (зазвичай <strong>+10</strong>) — на балансі з <strong>наступного дня о 00:00 за Києвом</strong>.</li>
          </ol>
          <p class="muted">Можуть діяти антифрод-ліміти (наприклад, кількість автоматичних нарахувань на добу). Умови може змінювати адміністратор мережі.</p>
        </div>

        <div class="panel legal-panel">
          <h3>7. Розсилка</h3>
          <p>Рекламні повідомлення бота можна вимкнути в меню бота «🔔 Розсилка» або кнопкою під рекламним постом. Службові сповіщення (кешбек, нарахування) можуть надсилатися незалежно від підписки на рекламу.</p>
        </div>

        <div class="panel legal-panel">
          <h3>8. Інше</h3>
          <ul class="legal-list">
            <li>Мережа може змінювати суми винагород і відсотки; актуальні значення — у мініапі / боті.</li>
            <li>Зловживання (фрод, кілька акаунтів тощо) може призвести до анулювання нарахувань.</li>
            <li>Питання: розділ «Підтримка» в боті.</li>
          </ul>
        </div>

        <p class="muted legal-foot">Ці правила стосуються програми лояльності Craft Coffee. Політика конфіденційності — окремий документ.</p>
        <button type="button" class="btn-quest legal-link-btn" data-tab-go="privacy">Політика конфіденційності</button>
      </div>`;
  }

  function privacyHtml() {
    return `
      <div class="legal-page">
        <button type="button" class="legal-back" data-legal-back>
          ← На головну
        </button>
        <div class="section-title">
          <div class="title-ico"><i data-lucide="shield"></i></div>
          <h2>Конфіденційність</h2>
        </div>
        <p class="muted legal-updated">Оновлено ${UPDATED} · власна політика мінізастосунку Craft Coffee</p>

        <div class="panel legal-panel">
          <h3>1. Хто ми</h3>
          <p>Оператор програми лояльності <strong>Craft Coffee</strong> (кавʼярні в Броварах) через Telegram-бота та мінізастосунок (Mini App).</p>
          <p class="muted">Це <strong>не</strong> політика конфіденційності Telegram. Telegram як платформа обробляє дані за своїми правилами. Нижче — як <em>ми</em> обробляємо дані саме для картки лояльності.</p>
        </div>

        <div class="panel legal-panel">
          <h3>2. Які дані збираємо</h3>
          <ul class="legal-list">
            <li><strong>Telegram ID</strong>, імʼя / username (з профілю Telegram).</li>
            <li><strong>Номер телефону</strong> — під час реєстрації картки (для клієнта на касі).</li>
            <li><strong>Імʼя для звернення</strong> — яке ти вказуєш у боті.</li>
            <li><strong>Дата народження</strong> — якщо надаєш (винагороди, персональні пропозиції).</li>
            <li><strong>Номер бонусної картки</strong>, стан Заряду / рівня кешбеку, історія нарахувань у нашій БД.</li>
            <li><strong>Дані покупок і бонусного балансу</strong> — через інтеграцію з касовою системою <strong>Poster</strong> (суми чеків, списання/нарахування).</li>
            <li>Дані реферальної програми (хто кого запросив) — якщо користуєшся «Приведи друга».</li>
            <li>Технічні дані сесії Mini App (<code>initData</code> Telegram) — для безпечного входу в застосунок.</li>
          </ul>
        </div>

        <div class="panel legal-panel">
          <h3>3. Навіщо</h3>
          <ul class="legal-list">
            <li>Оформити й обслуговувати картку лояльності.</li>
            <li>Нараховувати / списувати бонуси на касі, рахувати кешбек і Заряд.</li>
            <li>Показувати баланс, історію, меню та заклади в мініапі.</li>
            <li>Вітальні / святкові / реферальні нарахування.</li>
            <li>Сервісні та (за згодою) рекламні повідомлення в боті.</li>
          </ul>
          <p>Правова підстава: виконання договору (програма лояльності) та згода на окремі опції (дата народження, маркетинг).</p>
        </div>

        <div class="panel legal-panel">
          <h3>4. Кому передаємо</h3>
          <ul class="legal-list">
            <li><strong>Poster</strong> — касова CRM (клієнт, картка, баланс, чеки).</li>
            <li><strong>Telegram</strong> — доставка повідомлень і робота Mini App (як платформа).</li>
            <li>Підрядники хостингу / інфраструктури бота — лише в обсязі, потрібному для роботи сервісу.</li>
          </ul>
          <p>Ми не продаємо персональні дані третім сторонам для їхнього маркетингу.</p>
        </div>

        <div class="panel legal-panel">
          <h3>5. Зберігання</h3>
          <p>Дані зберігаються, поки активна картка / акаунт у боті, та стільки, скільки потрібно для обліку лояльності й вимог закону. Після видалення акаунту або запиту на видалення — видаляємо або анонімізуємо дані в нашій БД у розумні строки; дані в Poster можуть лишатися за правилами касової системи.</p>
        </div>

        <div class="panel legal-panel">
          <h3>6. Твої права</h3>
          <ul class="legal-list">
            <li>Дізнатися, які дані ми маємо, виправити неточності (імʼя, телефон через підтримку).</li>
            <li>Відкликати згоду на рекламну розсилку (меню «🔔 Розсилка»).</li>
            <li>Попросити видалення даних / закриття картки — через «Підтримка» в боті.</li>
          </ul>
        </div>

        <div class="panel legal-panel">
          <h3>7. Безпека</h3>
          <p>Доступ до Mini App захищений перевіркою підпису Telegram <code>initData</code>. Адмін-доступ до бота обмежений. Повністю виключити ризики в інтернеті неможливо — ми застосовуємо розумні технічні й організаційні заходи.</p>
        </div>

        <div class="panel legal-panel">
          <h3>8. Діти</h3>
          <p>Сервіс не орієнтований на дітей молодше 16 років без участі батьків / опікунів.</p>
        </div>

        <div class="panel legal-panel">
          <h3>9. Зміни</h3>
          <p>Можемо оновлювати цю політику. Актуальна версія завжди в мініапі; дата оновлення — на початку документа.</p>
        </div>

        <div class="panel legal-panel">
          <h3>10. Контакти</h3>
          <p>З питань персональних даних і картки: розділ <strong>«Підтримка»</strong> у Telegram-боті Craft Coffee.</p>
        </div>

        <button type="button" class="btn-quest legal-link-btn" data-tab-go="rules">Правила програми лояльності</button>
      </div>`;
  }

  global.CraftLegal = { rulesHtml, privacyHtml, UPDATED };
})(window);
