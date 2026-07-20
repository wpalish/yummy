/* ---- документы (демо-версии) ---- */
const LEGAL={
 offer:["Публичная оферта",`<p style="color:var(--txt2);font-size:.8rem"><i>Рабочая редакция. Перед публичным применением проверяется юристом РК. Полный текст — в репозитории (/legal/oferta.md).</i></p>
  <p><b>1. Предмет.</b> Yummy — платформа-агент: соединяет заведения-партнёры и покупателей для продажи сюрприз-боксов из свежих непроданных за день товаров. Продавцом и ответственным за качество является Партнёр.</p>
  <p><b>2. Заказ и оплата.</b> Покупатель оплачивает бокс онлайн и получает код/QR. Оплата — предоплата брони; средства перечисляются Партнёру за вычетом вознаграждения Сервиса после выдачи.</p>
  <p><b>3. Выдача.</b> По коду/QR в окне самовывоза. Состав бокса — сюрприз; претензии «попался не тот набор» не принимаются, если товар свежий и соответствует категории.</p>
  <p><b>4. Возвраты.</b> Не забрал в окне — бронь сгорает, предоплата не возвращается (товар был зарезервирован). Партнёр не выдал — полный возврат. Претензия к качеству — рассмотрение до 3 рабочих дней, при подтверждении возврат.</p>
  <p><b>5. Ответственность и права.</b> За безопасность еды отвечает Партнёр по законам РК. О пищевой аллергии сообщать Партнёру до получения. Оферта не ограничивает права по Закону РК «О защите прав потребителей».</p>`],
 privacy:["Политика конфиденциальности",`<p style="color:var(--txt2);font-size:.8rem"><i>Составлена с опорой на Закон РК «О персональных данных» № 94-V. Рабочая редакция, /legal/privacy.md.</i></p>
  <p><b>1. Данные.</b> Email, хеш пароля, имя, телефон, история заказов, аудит-лог (IP/время) — для входа, выдачи, возвратов и безопасности. Данные банковских карт и CVV НЕ собираем и НЕ храним — оплата на стороне провайдера.</p>
  <p><b>2. Согласие.</b> При регистрации даётся явное согласие на обработку (ст. 8 № 94-V). Отзыв = удаление аккаунта.</p>
  <p><b>3. Передача.</b> Заведению — имя и телефон только по оплаченному заказу. Провайдеру — сумма платежа. Третьим лицам не передаём и не продаём.</p>
  <p><b>4. Защита.</b> Пароли — только солёный хеш (PBKDF2), в открытом виде никогда. Доступ по ролям/токенам.</p>
  <p><b>5. Ваши права (реализованы в приложении).</b> Скачать свои данные · удалить аккаунт (обезличивание PII) · выйти со всех устройств · отозвать согласие.</p>`],
 quality:["Стандарты пищевой безопасности",`<p style="color:var(--txt2);font-size:.8rem"><i>Согласуются с санитарными требованиями РК (ТР ТС 021/2011, СанПиН). /legal/food-safety.md.</i></p>
  <p><b>Что продаётся:</b> только свежий товар текущего дня в допустимом окне реализации. Просрочка, вчерашний, повторно размороженный — запрещены.</p>
  <p><b>Хранение и выдача:</b> температурный режим; чистая пищевая упаковка; самовывоз строго день в день; окно самовывоза — в пределах пригодности товара.</p>
  <p><b>Аллергены:</b> состав заранее не публикуется, поэтому по запросу покупателя персонал обязан устно сообщить о наличии основных аллергенов (орехи, глютен, молоко, яйцо).</p>
  <p><b>Ответственность:</b> за качество отвечает заведение по законам РК. Жалоба → проверка → возврат; при повторных нарушениях — отключение партнёра.</p>`],
 agreement:["Договор с заведением",`<p style="color:var(--txt2);font-size:.8rem"><i>Агентский договор-оферта. Рабочая редакция, /legal/partner-agreement.md.</i></p>
  <p><b>Модель.</b> Yummy — агент: платформа + приём оплаты от имени заведения. Заведение — продавец.</p>
  <p><b>Вознаграждение и выплаты.</b> Комиссия сервиса __% с выданного заказа (на пилоте — 0%). Выплаты заведению — раз в неделю (по средам) за вычетом комиссии.</p>
  <p><b>Обязанности заведения.</b> Свежий товар дня, санитарные нормы РК, выдача по коду/QR в окне, достоверная категория/состав, обученный персонал.</p>
  <p><b>Обязанности сервиса.</b> Работа платформы, приём оплаты, своевременные выплаты, отчёт по заказам, неразглашение данных.</p>
  <p><b>Споры.</b> Обоснованная жалоба → возврат + объяснение партнёра. Систематические нарушения → приостановка/прекращение. Расторжение — с уведомлением за 7 дней.</p>`],
};
window.showLegal=k=>{const [t,body]=LEGAL[k];
  showModal(`<div class="mc"><h3>${t}</h3><div class="legal-txt">${body}</div>
  <button class="btn sec" data-act="closeModal" style="margin-top:.9rem">Закрыть</button></div>`);};

/* ---- модалка ---- */
function showModal(html){const m=$("#modal");m.className="modal-bg";
  m.innerHTML=`<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  m.onclick=e=>{if(e.target===m)closeModal();};
  const inp=m.querySelector("input,button");if(inp)inp.focus();}
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("#modal").classList.contains("hidden"))closeModal();});
window.closeModal=()=>{$("#modal").className="hidden";$("#modal").innerHTML="";if(!$("#view-store").classList.contains("hidden"))renderMyOrders();};

/* ---- уведомление о хранении данных ---- */
$("#yr").textContent=new Date().getFullYear();
if(!localStorage.getItem("ym_cookies")){
  const cb=document.createElement("div");cb.className="cookiebar";
  cb.innerHTML=`<span>Данные (коды заказов, избранное, фильтры) хранятся только в вашем браузере — localStorage. Cookies не используем.</span><button>Понятно</button>`;
  cb.querySelector("button").onclick=()=>{localStorage.setItem("ym_cookies","1");cb.remove();};
  document.body.appendChild(cb);
}

/* Telegram-канал в футере — показываем, только если handle настроен на бэке */
if(TG_CHANNEL){const cl=$("#tgChanLink");if(cl){cl.href=tgChannelUrl();cl.classList.remove("hidden");}}

/* PWA: установка на телефон + оффлайн-доступ к купленным кодам */
if("serviceWorker" in navigator){navigator.serviceWorker.register("/static/sw.js").catch(()=>{});}

/* Кнопка «Установить приложение» (паттерн из Google WebFundamentals):
   перехватываем системный баннер и показываем свою кнопку в футере */
let _bip=null;
window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();_bip=e;$("#installBtn").classList.remove("hidden");});
window.addEventListener("appinstalled",()=>{$("#installBtn").classList.add("hidden");toast("Yummy установлен 📲");});
$("#installBtn").onclick=async()=>{if(!_bip)return;_bip.prompt();try{await _bip.userChoice;}catch(e){} _bip=null;$("#installBtn").classList.add("hidden");};

/* Живые дашборды (реактивность в духе marimo): админка/партнёрка сами
   подтягивают свежие заказы, без F5 — только когда вкладка видима */
setInterval(()=>{
  if(document.hidden)return;
  if(window.__view==="admin")loadAdmin();
  else if(window.__view==="partner"&&$("#pSelect").value)loadPartnerData();
},15000);

/* Pull-to-refresh на мобиле (паттерн vux/WeUI) */
let _ptrY=0,_ptrOn=false;
document.addEventListener("touchstart",e=>{
  if(window.scrollY===0&&(window.__view==="store"||window.__view==="venues")){_ptrY=e.touches[0].clientY;_ptrOn=true;}
},{passive:true});
document.addEventListener("touchmove",e=>{
  if(!_ptrOn)return;
  const d=e.touches[0].clientY-_ptrY, el=$("#ptr");
  if(d>25&&window.scrollY===0){el.classList.remove("hidden");el.style.top=Math.min(d-25,70)+"px";el.style.transform=`translateX(-50%) rotate(${d*2}deg)`;}
},{passive:true});
document.addEventListener("touchend",()=>{
  if(!_ptrOn)return;_ptrOn=false;
  const el=$("#ptr"), d=parseInt(el.style.top)||0;
  el.classList.add("hidden");el.style.top="-60px";
  if(d>=60){toast("Обновляем…");window.__view==="venues"?loadVenues():loadStore();}
});

renderAccount();

window.__view="store";
if(!account())switchView("landing");   // первый заход — лендинг-история со скроллом до регистрации
restoreSession().then(ok=>{            // access-токен вернулся по httpOnly-cookie
  if(ok)renderAccount();
  else if(account()&&account().server){ // cookie умер (логаут/30 дней) — честно разлогинить
    localStorage.removeItem("ym_account"); renderAccount();
  }
});
loadStore().then(()=>{
  // deep-link: ?box=id — открыть карточку бокса из расшаренной ссылки
  const qs=new URLSearchParams(location.search);
  const bid=qs.get("box"); if(bid)openBox(bid);
  // ярлыки PWA (manifest shortcuts): ?nav=orders|venues
  const nav=qs.get("nav");
  if(nav==="venues")switchView("venues"); else if(nav==="orders")gotoOrders();
  // ссылка-приглашение от админа: ?invite=<токен> — единственный путь в партнёрку
  const inv=qs.get("invite"); if(inv)acceptInviteForm(inv);
  // ссылка сброса пароля из письма: ?reset=<токен>
  const rst=qs.get("reset"); if(rst)resetPwForm(rst);
});

/* ============ ПРИГЛАШЕНИЕ ПЕРСОНАЛА (ссылка от админа) ============ */
const STAFF_ROLE_RU={owner:"владелец заведения",manager:"менеджер",cashier:"кассир"};
async function acceptInviteForm(token){
  let inv;
  try{ inv=await get("/auth/invite/"+encodeURIComponent(token)); }
  catch(e){ toast("Приглашение недействительно или истекло",true); return; }
  showModal(`<div class="mc">
    <h3>Приглашение в Yummy</h3>
    <p style="font-size:.85rem;color:var(--txt2);margin:.3rem 0 .9rem">
      Вас приглашают как <b style="color:var(--brown)">${esc(STAFF_ROLE_RU[inv.partner_role]||inv.partner_role)}</b>${inv.brand_name?` · ${esc(inv.brand_name)}`:""}.<br>
      Аккаунт: <b>${esc(inv.email)}</b></p>
    <label>Придумайте пароль <input id="ivPass" type="password" placeholder="Минимум 8 символов, буквы и цифры" autocomplete="new-password" /></label>
    <button class="btn" id="ivBtn" style="margin-top:.8rem">Принять приглашение</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Позже</button>
  </div>`);
  $("#ivBtn").onclick=async()=>{
    const b=$("#ivBtn"); b.disabled=true; b.textContent="Активируем…";
    try{
      const r=await post("/auth/accept-invite",{token,password:$("#ivPass").value});
      setAccount({name:r.user.brand_name||r.user.email,role:r.user.role,
                  token:r.access_token,refresh:r.refresh_token,
                  partner_role:r.user.partner_role,partner_id:r.user.partner_id});
      closeModal(); toast("Добро пожаловать в Yummy 🎉");
      history.replaceState({},"",location.pathname);   // убрать токен из адресной строки
      switchView("partner");
    }catch(e){ toast(e.message,true); b.disabled=false; b.textContent="Принять приглашение"; }
  };
}
