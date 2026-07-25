/* ============ ЛИЧНЫЙ КАБИНЕТ ПОКУПАТЕЛЯ ============ */
/* Дашборд «Мой вклад», таблица заказов, избранные заведения, настройки.
   Данные те же, что в renderMyOrders (/me/orders или локальные коды) —
   ничего не выдумываем: экономия помечена «≈», т.к. Order не хранит value_est. */
let accTab="dash", ACC_ORDERS=[];

async function fetchMyOrders(){
  const a=account();
  if(a&&a.token){ try{ return await get("/me/orders"); }catch(e){} }
  const codes=myCodes();
  if(!codes.length)return [];
  return (await Promise.all(codes.map(c=>get("/orders/"+c).catch(()=>null)))).filter(Boolean);
}
async function loadAccount(){
  $("#accBody").innerHTML='<p class="empty">Загружаем…</p>';
  ACC_ORDERS=await fetchMyOrders();
  renderAccTab();
}
document.querySelectorAll(".accnav button").forEach(b=>b.onclick=()=>{
  accTab=b.dataset.tab;
  document.querySelectorAll(".accnav button").forEach(x=>x.classList.toggle("on",x===b));
  renderAccTab();
});
function renderAccTab(){
  const el=$("#accBody");
  if(accTab==="dash")el.innerHTML=dashHtml();
  else if(accTab==="orders")el.innerHTML=`<h2 class="acch">Мои заказы</h2>${ordersTable(ACC_ORDERS)}`;
  else if(accTab==="favs")el.innerHTML=`<h2 class="acch">Избранное</h2><div id="savedWrap"></div>`;
  else el.innerHTML=settingsHtml();
  if(accTab==="favs")renderSaved();
}
/* Вклад считаем ТОЛЬКО по выданным заказам — забронированный, но не забранный
   бокс еду ещё не спас. */
function impactOf(orders){
  const done=orders.filter(o=>o.status==="issued");
  return {
    n:done.length,
    kg:(done.length*ECO_KG).toFixed(1),
    co2:(done.length*ECO_CO2).toFixed(1),
    saved:Math.round(done.reduce((s,o)=>s+o.price,0)*1.5),
  };
}
function dashHtml(){
  const im=impactOf(ACC_ORDERS);
  const recent=ACC_ORDERS.slice(0,5);
  return `<h2 class="acch">Мой вклад</h2>
    <div class="impact">
      <div><span class="ic" aria-hidden="true">🌱</span>
        <div><b>${im.kg} кг</b><span>спасено еды · ~${im.co2} кг CO₂</span></div></div>
      <div><span class="ic" aria-hidden="true">🐖</span>
        <div><b>≈${money(im.saved)}</b><span>сэкономлено на боксах</span></div></div>
    </div>
    ${im.n?"":'<p class="empty" style="margin:-1rem 0 1.6rem">Пока пусто — заберите первый бокс, и здесь появится ваш вклад.</p>'}
    <h2 class="acch">Последние заказы</h2>${ordersTable(recent)}`;
}
const ST_TAG={paid:"t-paid",issued:"t-issued",expired:"t-expired",cancelled:"t-expired",refunded:"t-expired"};
function ordersTable(orders){
  if(!orders.length)return '<p class="empty">Заказов пока нет.</p>';
  return `<div class="otwrap"><table class="otable">
    <thead><tr><th>№ заказа</th><th>Заведение</th><th>Статус</th><th>Забрать</th><th>Действие</th></tr></thead>
    <tbody>${orders.map(o=>`<tr>
      <td class="cd">${esc(o.code)}</td>
      <td>${esc(o.partner_name)}<div style="font-size:.74rem;color:var(--txt2)">${money(o.price)}</div></td>
      <td><span class="tag ${ST_TAG[o.status]||"t-expired"}">${STATUS_RU[o.status]||esc(o.status)}</span></td>
      <td style="font-size:.8rem;color:var(--txt2)">${win(o.pickup_from,o.pickup_to)}</td>
      <td><button class="linkbtn" data-act="showCode" data-a1="${esc(o.code)}">Показать код</button></td>
    </tr>`).join("")}</tbody></table></div>`;
}
/* Избранное: в localStorage лежат partner_id — названия и фото берём из /partners */
async function renderSaved(){
  const wrap=$("#savedWrap"); if(!wrap)return;
  const ids=favs();
  if(!ids.length){wrap.innerHTML='<p class="empty">Нет сохранённых заведений. Нажмите ♥ на карточке бокса.</p>';return;}
  let ps=[]; try{ps=await get("/partners");}catch(e){}
  const mine=ps.filter(p=>ids.includes(p.id));
  if(!mine.length){wrap.innerHTML='<p class="empty">Сохранённые заведения сейчас недоступны.</p>';return;}
  wrap.innerHTML=`<div class="savg">${mine.map(p=>`<article class="savc">
    <img src="${venuePhotoFor(p.id)}" alt="" loading="lazy">
    <div class="n"><b>${esc(p.name)}</b>
      <button class="hb" title="Убрать из избранного" data-act="unsaveVenue" data-a1="${esc(p.id)}">♥</button></div>
  </article>`).join("")}</div>`;
}
// то же детерминированное фото, что и в справочнике заведений
function venuePhotoFor(id){
  let h=0; for(const ch of String(id))h=(h*31+ch.charCodeAt(0))>>>0;
  return "/static/img/"+VENUE_PHOTOS[h%VENUE_PHOTOS.length];
}
window.unsaveVenue=pid=>{ toggleFav(pid); renderSaved(); };
function settingsHtml(){
  const a=account()||{};
  return `<h2 class="acch">Настройки</h2>
    <div class="cardp">
      <div class="row"><span>Имя</span><b>${esc(a.name||"—")}</b></div>
      <div class="row"><span>Роль</span><b>${ROLE_RU[a.role]||"гость"}</b></div>
      ${a.phone?`<div class="row"><span>Телефон</span><b>${esc(a.phone)}</b></div>`:""}
      <p style="font-size:.78rem;color:var(--txt2);margin:.8rem 0 0">
        Смена пароля, выгрузка данных и удаление аккаунта — в меню профиля справа вверху.</p>
    </div>`;
}
