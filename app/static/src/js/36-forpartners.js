/* ============ СТРАНИЦА ДЛЯ ЗАВЕДЕНИЙ ============ */
/* Отдельный вид с прямой ссылкой ?partners — чтобы кидать её в WhatsApp/директ
   при холодных контактах вместо объяснений текстом. */

/* Заявка: собираем данные и отдаём пользователю выбор канала. Своего эндпоинта
   для заявок нет — не выдумываем несуществующую отправку, а честно открываем
   почту/телеграм с уже заполненным текстом. */
window.fpApply=()=>{
  showModal(`<div class="mc">
    <h3>Заявка на подключение</h3>
    <p class="sub" style="margin:.1rem 0 .8rem">Заполните — и мы свяжемся в течение дня.</p>
    <label>Название заведения <input id="fpName" placeholder="Напр.: Бриошь" autocomplete="organization" /></label>
    <label>Адрес <input id="fpAddr" placeholder="Улица, дом" /></label>
    <label>Телефон или WhatsApp <input id="fpPhone" placeholder="+7 7XX XXX XX XX" autocomplete="tel" /></label>
    <span class="ferr" id="fpErr"></span>
    <button class="btn" id="fpSend" style="margin-top:.6rem">✉️ Отправить на почту</button>
    <a class="btn sec" id="fpTg" style="display:block;text-decoration:none;margin-top:.5rem"
       href="https://t.me/yummy_astana_bot" target="_blank" rel="noopener">💬 Написать в Telegram</a>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Закрыть</button>
  </div>`);
  $("#fpSend").onclick=()=>{
    const n=$("#fpName").value.trim(), a=$("#fpAddr").value.trim(), p=$("#fpPhone").value.trim();
    if(!n||!p){ $("#fpErr").textContent="Укажите название и контакт"; return; }
    const body=`Заведение: ${n}\nАдрес: ${a}\nКонтакт: ${p}\n`;
    location.href="mailto:alisher.nursain@gmail.com"
      +"?subject="+encodeURIComponent("Заявка на подключение к Yummy")
      +"&body="+encodeURIComponent(body);
    closeModal(); toast("Открываем почту — отправьте письмо 💌");
  };
};
