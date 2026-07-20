/* ============ ЗАВЕДЕНИЯ (137 точек Zebra/Espresso Day из 2GIS) ============ */
let ALL_VENUES=null, curChain="all", curVDist="all", vmapObj=null, vmapMode=false;
const CHAIN_META={"Espresso Day":{cls:"esp",ic:"☕"},"Zebra Coffee":{cls:"zeb",ic:"🦓"}};
async function fetchVenues(){
  if(ALL_VENUES)return ALL_VENUES;
  for(const u of ["/static/venues.json","venues.json"]){
    try{const r=await fetch(u); if(r.ok){ALL_VENUES=await r.json(); return ALL_VENUES;}}catch(e){}
  }
  ALL_VENUES=[]; return ALL_VENUES;
}
async function loadVenues(){
  const vs=await fetchVenues();
  // фильтр по сети
  const chains=[...new Set(vs.map(v=>v.chain))];
  $("#chainFilter").innerHTML=[`<button class="${curChain==="all"?"on":""}" data-c="all">Все сети · ${vs.length}</button>`]
    .concat(chains.map(c=>`<button class="${curChain===c?"on":""}" data-c="${esc(c)}">${CHAIN_META[c]?.ic||""} ${esc(c)} · ${vs.filter(v=>v.chain===c).length}</button>`)).join("");
  document.querySelectorAll("#chainFilter button").forEach(b=>b.onclick=()=>{curChain=b.dataset.c;loadVenues();});
  // районы с počтом
  let pool=curChain==="all"?vs:vs.filter(v=>v.chain===curChain);
  const dists=[...new Set(pool.map(v=>v.district))].sort((a,b)=>pool.filter(v=>v.district===b).length-pool.filter(v=>v.district===a).length);
  $("#vDistricts").innerHTML=[`<button class="dist${curVDist==="all"?" on":""}" data-d="all">Все районы · ${pool.length}</button>`]
    .concat(dists.map(d=>`<button class="dist${curVDist===d?" on":""}" data-d="${esc(d)}">${esc(d)} · ${pool.filter(v=>v.district===d).length}</button>`)).join("");
  document.querySelectorAll("#vDistricts .dist").forEach(b=>b.onclick=()=>{curVDist=b.dataset.d;loadVenues();});
  renderVenues();
  if(vmapMode)renderVMap();
}
function venuesFiltered(){
  let vs=ALL_VENUES||[];
  if(curChain!=="all")vs=vs.filter(v=>v.chain===curChain);
  if(curVDist!=="all")vs=vs.filter(v=>v.district===curVDist);
  return vs;
}
function vCard(v){
  const m=CHAIN_META[v.chain]||{cls:"",ic:"☕"};
  return `<article class="vcard" data-id="${v.id}">
    <div class="logo ${m.cls}">${m.ic}</div>
    <div class="b">
      <h3>${esc(v.chain)}</h3>
      <div class="addr">${esc(v.addr)} · ${esc(v.district)}</div>
      <div class="meta">
        ${v.rating?`<span class="star">⭐ ${v.rating}${v.reviews?` · ${v.reviews}`:""}</span>`:""}
        <span class="pill gr">📍 на карте</span>
      </div>
    </div></article>`;
}
function renderVenues(){
  const vs=venuesFiltered();
  $("#vTitle").textContent=`Заведения${vs.length?` · ${vs.length}`:""}`;
  const list=$("#venueList");
  if(!vs.length){list.innerHTML='<p class="vempty">Ничего не нашлось в этом фильтре.</p>';return;}
  if(curVDist!=="all"){ list.innerHTML=vs.map(vCard).join(""); }
  else{ // группировка по районам
    const byD={}; vs.forEach(v=>{(byD[v.district]=byD[v.district]||[]).push(v);});
    const order=Object.keys(byD).sort((a,b)=>byD[b].length-byD[a].length);
    list.style.display="block";
    list.innerHTML=order.map(d=>`<div class="vgroup-h"><h3>${esc(d)}</h3><span>${byD[d].length} ${plural(byD[d].length,["заведение","заведения","заведений"])}</span></div>
      <div class="venues" style="margin-bottom:.4rem">${byD[d].map(vCard).join("")}</div>`).join("");
  }
  if(curVDist!=="all"){list.style.display="grid";}
  document.querySelectorAll(".vcard").forEach(el=>el.onclick=()=>openVenue(el.dataset.id));
}
$("#vvList").onclick=()=>{vmapMode=false;$("#vvList").classList.add("on");$("#vvMap").classList.remove("on");$("#vmap").classList.add("hidden");$("#venueList").classList.remove("hidden");};
$("#vvMap").onclick=()=>{vmapMode=true;$("#vvMap").classList.add("on");$("#vvList").classList.remove("on");$("#venueList").classList.add("hidden");$("#vmap").classList.remove("hidden");renderVMap();};
function renderVMap(){
  const vs=venuesFiltered();
  if(!vmapObj){
    vmapObj=L.map("vmap").setView([51.13,71.43],11);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(vmapObj);
  }
  setTimeout(()=>vmapObj.invalidateSize(),80);
  if(vmapObj._mk)vmapObj._mk.forEach(m=>m.remove());
  vmapObj._mk=vs.map(v=>{
    const color=v.chain==="Zebra Coffee"?"#2b2b2b":"#6F4E37";
    const mk=L.circleMarker([v.lat,v.lon],{radius:6,fillColor:color,color:"#fff",weight:1.5,fillOpacity:.9}).addTo(vmapObj);
    mk.bindPopup(`<b>${esc(v.chain)}</b><br>${esc(v.addr)}<br>${esc(v.district)}${v.rating?" · ⭐ "+v.rating:""}<br><button data-act="openVenue" data-a1="${v.id}" style="margin-top:6px;width:100%;background:oklch(22% .03 45);border:0;padding:7px;border-radius:999px;font-weight:700;color:oklch(97% .018 82);cursor:pointer">Подробнее</button>`);
    return mk;
  });
  if(vs.length){const g=L.featureGroup(vmapObj._mk); try{vmapObj.fitBounds(g.getBounds().pad(0.1));}catch(e){}}
}
const CAT_EMO={sweet:"🍩",bakery:"🥐",mixed:"🧺",snack:"🥪"};
window.openVenue=id=>{
  const v=(ALL_VENUES||[]).find(x=>x.id===id); if(!v)return;
  const m=CHAIN_META[v.chain]||{ic:"☕"};
  showModal(`<div class="mc">
    <div style="display:flex;gap:.7rem;align-items:center">
      <div class="logo ${m.cls}" style="width:52px;height:52px;border-radius:13px;display:grid;place-items:center;font-size:1.6rem;color:#fff">${m.ic}</div>
      <div><h3 style="margin:0">${esc(v.chain)}</h3><div style="font-size:.8rem;color:var(--txt2)">${esc(v.addr)} · ${esc(v.district)}${v.rating?" · ⭐ "+v.rating:""}</div></div>
    </div>
    <a href="https://2gis.kz/astana/firm/${v.id}" target="_blank" rel="noopener" style="display:inline-block;margin:.6rem 0 .2rem;font-size:.78rem;font-weight:700">🗺 Открыть в 2ГИС →</a>
    <div class="rules" style="margin-top:.7rem"><b>Заведение ещё не в Yummy.</b> Это кофейня из карты Астаны, которую мы хотим подключить. Как только она начнёт продавать вечерние излишки — здесь появятся боксы со скидкой.</div>
    <button class="btn" style="margin-top:.7rem" data-act="callVenue" data-a1="${esc(v.id)}">📣 Хочу боксы отсюда</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Закрыть</button>
  </div>`);
};
/* «Позвать заведение» — честный интерес вместо фейковой брони.
   Голос уходит на бэкенд (счётчик спроса, без персональных данных) и копится
   локально, чтобы не голосовать дважды. Бэкенд недоступен → тихо остаётся локальным. */
window.callVenue=async id=>{
  const v=(ALL_VENUES||[]).find(x=>x.id===id); if(!v)return;
  const key="ym_called", called=JSON.parse(localStorage.getItem(key)||"[]");
  closeModal();
  if(called.includes(id)){toast(`Мы уже знаем — ${v.chain} в очереди на подключение 💛`);return;}
  called.push(id); localStorage.setItem(key,JSON.stringify(called));
  try{ await post("/venues/interest",{venue_id:v.id,name:v.chain,address:v.addr,district:v.district}); }
  catch(e){ /* офлайн/статик — голос всё равно засчитан локально */ }
  toast(`Спасибо! Передадим ${v.chain}, что их ждут в Yummy 💛`);
};
/* отзывы (демо) */
window.showReviews=async(partnerId,name)=>{
  showModal(`<div class="mc"><h3>${esc(name)}</h3><p style="font-size:.82rem;color:var(--txt2)">Загружаем отзывы…</p></div>`);
  let real=[];
  try{real=await get(`/partners/${partnerId}/reviews`);}catch(e){}
  const body=real.length
    ? `<p style="font-size:.76rem;color:var(--txt2);margin:.15rem 0 .5rem">Отзывы покупателей — только по подтверждённым заказам</p>
       ${real.map(r=>`<div class="rev"><b>${esc(r.author_name)}</b> <span class="st">${"★".repeat(r.rating)}${"☆".repeat(5-r.rating)}</span><br>${esc(r.text)}</div>`).join("")}`
    : DEMO_PAY
      // демо-примеры отзывов — только в пилоте и с явной пометкой; в проде их нет
      ? `<p style="font-size:.76rem;color:var(--txt2);margin:.15rem 0 .5rem">Реальных отзывов пока нет — вот примеры того, как это будет выглядеть (демо):</p>
       ${(REVIEWS[name]||[["Гость","Пока нет отзывов — будь первым!",5]]).map(([n,t,s])=>`<div class="rev"><b>${esc(n)}</b> <span class="st">${"★".repeat(s)}${"☆".repeat(5-s)}</span><br>${esc(t)}</div>`).join("")}`
      : `<p style="font-size:.82rem;color:var(--txt2);margin:.15rem 0 .5rem">Отзывов пока нет — станьте первым после заказа.</p>`;
  showModal(`<div class="mc"><h3>${esc(name)}</h3>${body}
    <button class="btn sec" data-act="closeModal" style="margin-top:.9rem">Закрыть</button></div>`);
};
async function openBox(id){
  let b;try{b=await get("/boxes/"+id);}catch(e){toast(e.message,true);return;}
  showModal(`<div class="mh" style="background-image:url(/static/img/${imgFor(b)})"><button class="x" data-act="closeModal">✕</button></div>
    <div class="mc">
      <div style="color:var(--txt2);font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.04em">${esc(b.category_ru)}</div>
      <h3>${esc(b.title||b.partner_name)}</h3>
      <div style="color:var(--txt2);font-size:.84rem">${esc(b.partner_name)} · ${esc(b.address)} · ⭐ ${b.rating}
        · <a href="${gisUrl(b.partner_name,b.address)}" target="_blank" rel="noopener" style="font-weight:700">🗺 Маршрут</a></div>
      <div class="row"><span>Цена</span><b>${money(b.price)} <s style="color:#A08D7D;font-weight:400">${money(b.value_est)}</s> <span style="color:var(--green);font-weight:800">−${b.discount}%</span></b></div>
      <div class="row"><span>Самовывоз</span><span>${win(b.pickup_from,b.pickup_to)}</span></div>
      <div class="row"><span>Осталось</span><span>${b.qty_left} из ${b.qty_total}</span></div>
      ${b.description?`<div class="inside"><b>Что обычно внутри:</b> ${esc(b.description)}</div>`:""}
      <div class="rules"><b>Сюрприз-бокс.</b> Точный состав может отличаться — это набор из свежих остатков дня. Забрать нужно в окне самовывоза, иначе заказ сгорает (предоплата не возвращается). Если заведение не выдаст — полный возврат.</div>
      ${DEMO_PAY?`<label>Ваше имя <input id="oName" placeholder="Имя" /></label>
      <label>Телефон <input id="oPhone" placeholder="+7 7XX XXX XX XX" /></label>
      <button class="btn" id="payBtn" style="margin-top:.8rem">Оплатить ${money(b.price)}</button>
      <div id="kaspiSlot"></div>`
      :`<div class="rules" style="border-color:var(--red)"><b>Покупка пока недоступна.</b> Заведение ещё не подключило приём платежей — как только подключит, бокс можно будет оплатить и забрать.</div>`}
      <button class="btn sec" id="shareBtn" style="margin-top:.5rem">🔗 Поделиться боксом</button>
      ${DEMO_PAY?`<div class="demo-pay">💳 Демо-оплата. В продакшене — Kaspi Pay / Kaspi QR.</div>`:""}
    </div>`);
  const acc=account();  // зарегистрированному покупателю подставляем имя/телефон
  if(DEMO_PAY&&acc&&acc.role==="buyer"){ if(acc.name)$("#oName").value=acc.name; if(acc.phone)$("#oPhone").value=acc.phone; }
  if(DEMO_PAY&&KASPI_SERVICE_ID){ // включается автоматически, когда появится service_id мерчанта
    $("#kaspiSlot").innerHTML=`<a href="https://kaspi.kz/pay/${encodeURIComponent(KASPI_SERVICE_ID)}?amount=${b.price}"
      style="display:block;text-align:center;background:#F14635;color:#fff;font-weight:800;padding:.8rem 1rem;border-radius:13px;margin-top:.5rem;text-decoration:none">Оплатить через Kaspi</a>`;
  }
  $("#shareBtn").onclick=async()=>{
    const url=location.origin+location.pathname+"?box="+encodeURIComponent(b.id);
    const data={title:"Yummy — "+(b.title||b.partner_name),text:`${b.title||b.partner_name} за ${money(b.price)} (скидка −${b.discount}%) в ${b.partner_name}`,url};
    try{ if(navigator.share){await navigator.share(data);} else {await navigator.clipboard.writeText(url);toast("Ссылка скопирована 🔗");} }
    catch(e){ try{await navigator.clipboard.writeText(url);toast("Ссылка скопирована 🔗");}catch(_){toast(url);} }
  };
  if(!DEMO_PAY)return;   // покупка недоступна — кнопки оплаты нет
  $("#payBtn").onclick=async()=>{
    const name=$("#oName").value.trim(), phone=$("#oPhone").value.trim();
    if(!name||phone.length<5){toast("Укажите имя и телефон",true);return;}
    $("#payBtn").disabled=true;$("#payBtn").textContent="Оплата…";
    try{
      const res=await post("/orders",{box_id:b.id,user_name:name,user_phone:phone});
      saveCode(res.order.code);
      const a=account(); if(a&&a.role==="buyer"&&!a.phone){a.phone=phone;setAccount(a);}  // запомнить телефон
      successScreen(res);
    }catch(e){toast(e.message,true);$("#payBtn").disabled=false;$("#payBtn").textContent="Оплатить "+money(b.price);}
  };
}
function successScreen(res){
  const o=res.order;
  if(o.payment_status==="pending"){ // бокс зарезервирован, ждём оплату (мерчант партнёра)
    showModal(`<div class="mc ok-wrap" style="padding-top:1.4rem">
      <div class="ok-ic">⏳</div>
      <h3>Бокс зарезервирован на 15 минут</h3>
      <p style="color:var(--txt2);font-size:.86rem;margin:.2rem 0 0">${esc(o.partner_name)} · ${esc(o.address)}</p>
      <div class="code">${esc(o.code)}</div>
      <p style="font-size:.84rem;color:var(--txt2);margin:.5rem 0">Оплата зачисляется напрямую заведению. QR откроется после оплаты.</p>
      <button class="btn" id="confirmPayBtn" style="margin-bottom:.5rem">Оплатить ${money(o.price)}</button>
      <div class="demo-pay">В продакшене — Kaspi Pay мерчанта заведения. Кнопка выше подтверждает оплату (пока нет Kaspi-интеграции).</div>
      <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Позже</button>
    </div>`);
    $("#confirmPayBtn").onclick=async()=>{
      const btn=$("#confirmPayBtn");btn.disabled=true;btn.textContent="Проверяем оплату…";
      try{const r=await post("/orders/confirm-payment",{code:o.code});successScreen(r);}
      catch(e){toast(e.message,true);btn.disabled=false;btn.textContent="Оплатить "+money(o.price);}
    };
    return;
  }
  showModal(`<div class="mc ok-wrap" style="padding-top:1.4rem">
    <div class="ok-ic">✅</div>
    <h3>Бокс забронирован!</h3>
    <p style="color:var(--txt2);font-size:.86rem;margin:.2rem 0 0">${esc(o.partner_name)} · ${esc(o.address)}</p>
    <div class="qr">${res.qr_svg}</div>
    <div class="code">${esc(o.code)}</div>
    <p style="font-size:.84rem;color:var(--txt2);margin:.5rem 0">Покажите код или QR на кассе.<br>Забрать: <b style="color:var(--brown)">${win(o.pickup_from,o.pickup_to)}</b></p>
    <p style="font-size:.8rem;color:var(--green);font-weight:700;margin:.3rem 0 .6rem">🌱 Вы спасли ~${ECO_KG} кг еды и предотвратили ~${ECO_CO2} кг CO₂</p>
    <a class="btn sec" style="display:block;text-decoration:none;margin-bottom:.5rem" href="${gisUrl(o.partner_name,o.address)}" target="_blank" rel="noopener">🗺 Маршрут в 2ГИС</a>
    <a class="btn sec" style="display:block;text-decoration:none;margin-bottom:.5rem" href="${tgChannelUrl()||"https://t.me/yummy_astana_bot"}" target="_blank" rel="noopener">🔔 Узнавать о новых боксах в Telegram</a>
    <button class="btn sec" data-act="closeModal">Готово</button>
  </div>`);
}
function myCodes(){try{return JSON.parse(localStorage.getItem("ym_codes")||"[]");}catch(e){return [];}}
function saveCode(c){const a=myCodes();if(!a.includes(c)){a.unshift(c);localStorage.setItem("ym_codes",JSON.stringify(a.slice(0,20)));}updateCart();}
function updateCart(){const n=myCodes().length;const el=$("#cartCnt");el.textContent=n;el.classList.toggle("hidden",!n);}
async function renderMyOrders(){
  updateCart();
  const el=$("#myorders"); const a=account();
  let orders=null;
  if(a&&a.token){ try{orders=await get("/me/orders");}catch(e){} }  // кросс-девайс история аккаунта
  if(!orders){
    const codes=myCodes();
    if(!codes.length){el.innerHTML="";return;}
    orders=(await Promise.all(codes.map(c=>get("/orders/"+c).catch(()=>null)))).filter(Boolean);
  }
  if(!orders.length){el.innerHTML="";return;}
  const done=orders.filter(o=>o.status==="issued");
  const eco=done.length?`<p style="margin:0 0 .6rem;font-size:.82rem;font-weight:700;color:var(--green)">🌱 Вы спасли ~${(done.length*ECO_KG).toFixed(1)} кг еды · ${(done.length*ECO_CO2).toFixed(1)} кг CO₂ · сэкономили ≈${money(Math.round(done.reduce((s,o)=>s+o.price,0)*1.5))}</p>`:"";
  const reviewed=reviewedIds();
  el.innerHTML=`<div class="cardp"><h3>Мои заказы</h3>${eco}${orders.map(o=>`<div class="lrow">
    <div style="font-size:1.3rem">${o.emoji}</div>
    <div class="g"><b>${esc(o.code)}</b> · ${esc(o.partner_name)}
      <div style="font-size:.76rem;color:var(--txt2)">${win(o.pickup_from,o.pickup_to)} · ${money(o.price)}</div>
      ${(o.status==="paid"&&Date.now()<Date.parse(o.pickup_from))?`<button class="linkbtn" data-act="cancelOrder" data-a1="${esc(o.code)}">Отменить бронь</button>`:""}
      ${(o.status==="paid"&&Date.now()>=Date.parse(o.pickup_from))?`<button class="linkbtn" data-act="userRefund" data-a1="${esc(o.code)}">Не выдали заказ? Вернуть деньги</button>`:""}
      ${(o.status==="issued"&&!reviewed.includes(o.id))?`<button class="linkbtn" data-act="leaveReviewForm" data-a1="${o.id}" data-a2="${o.partner_id}" data-a3="${esc(o.partner_name)}">⭐ Оставить отзыв</button>`:""}
      <button class="linkbtn" data-act="showCode" data-a1="${esc(o.code)}">Показать код и QR</button></div>
    <span class="tag t-${o.status}">${STATUS_RU[o.status]}</span></div>`).join("")}</div>`;
}
function reviewedIds(){try{return JSON.parse(localStorage.getItem("ym_reviewed")||"[]");}catch(e){return [];}}
function markReviewed(id){const r=reviewedIds();if(!r.includes(id)){r.push(id);localStorage.setItem("ym_reviewed",JSON.stringify(r));}}
window.leaveReviewForm=(orderId,partnerId,partnerName)=>{
  showModal(`<div class="mc">
    <h3>Отзыв о ${esc(partnerName)}</h3>
    <label>Оценка <select id="rvStars"><option value="5">★★★★★ Отлично</option><option value="4">★★★★☆ Хорошо</option>
      <option value="3">★★★☆☆ Нормально</option><option value="2">★★☆☆☆ Так себе</option><option value="1">★☆☆☆☆ Плохо</option></select></label>
    <label>Комментарий <textarea id="rvText" rows="3" placeholder="Что понравилось или нет?"></textarea></label>
    <span class="ferr" id="rv_err"></span>
    <button class="btn" id="rvSend" style="margin-top:.6rem">Отправить отзыв</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#rvSend").onclick=async()=>{
    const text=$("#rvText").value.trim();
    if(text.length<3){$("#rv_err").textContent="Напишите пару слов";return;}
    const btn=$("#rvSend"); btn.disabled=true; btn.textContent="Отправляем…";
    try{
      await post(`/partners/${partnerId}/reviews`,{order_id:orderId,rating:+$("#rvStars").value,text});
      markReviewed(orderId); closeModal(); toast("Спасибо за отзыв! ⭐"); renderMyOrders();
    }catch(e){
      if(/уже оставлен/i.test(e.message))markReviewed(orderId);
      $("#rv_err").textContent=e.message; btn.disabled=false; btn.textContent="Отправить отзыв";
    }
  };
};
window.showCode=code=>{
  // QR рисуем на месте, если библиотека есть (Pages-версия); иначе — крупный код
  let qr="";
  try{ if(typeof qrcode==="function"){const q=qrcode(0,"M");q.addData(code);q.make();qr=`<div class="qr">${q.createSvgTag({cellSize:6,margin:2})}</div>`;} }catch(e){}
  showModal(`<div class="mc ok-wrap" style="padding-top:1.3rem">
    <h3>Код выдачи</h3>${qr}
    <div class="code">${esc(code)}</div>
    <p style="font-size:.84rem;color:var(--txt2);margin:.5rem 0">Покажите ${qr?"QR или ":""}код на кассе заведения.</p>
    <button class="btn sec" data-act="closeModal">Закрыть</button></div>`);
};
window.userRefund=async code=>{
  if(!confirm("Вернуть деньги? Используйте, только если заведение не выдало заказ."))return;
  try{const r=await post("/orders/refund",{code});toast(r.message||"Возврат оформлен — деньги вернутся на карту");renderMyOrders();loadStore();}
  catch(e){toast(e.message,true);}
};
window.cancelOrder=async code=>{
  if(!confirm("Отменить бронь? Бокс вернётся в продажу, деньги — на карту."))return;
  try{const r=await post("/orders/cancel",{code});toast(r.message||"Бронь отменена");renderMyOrders();loadStore();}
  catch(e){toast(e.message,true);}
};

