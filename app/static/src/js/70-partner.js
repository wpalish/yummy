/* ============ ПАРТНЁР ============ */
async function loadPartner(){
  let ps=[];try{ps=await get("/partners");}catch(e){}
  if(!$("#pSelect").dataset.filled){
    $("#pSelect").innerHTML=ps.map(p=>`<option value="${p.id}">${esc(p.name)} · ${esc(p.district)}</option>`).join("");
    $("#pSelect").dataset.filled="1";
    $("#pSelect").onchange=loadPartnerData;
  }
  loadTotp();   // карточка 2FA в кабинете (обязательна для владельца)
  loadPartnerData();
}
function curPartner(){return $("#pSelect").value;}
async function loadPartnerData(){
  const pid=curPartner();
  {const cb=$("#pCsv"); if(cb)cb.onclick=()=>downloadCsv(`/partners/${pid}/orders.csv`,"yummy-orders.csv");}
  let boxes=[],orders=[];
  try{boxes=await get(`/partners/${pid}/boxes`);}catch(e){}
  try{orders=await get(`/partners/${pid}/orders`);}catch(e){}
  renderTemplates();
  // мини-аналитика точки (семя CRM-тарифа): выручка, продажи, выкуп, остаток
  const done=orders.filter(o=>o.status==="issued"), act=orders.filter(o=>o.status==="paid");
  const noshow=orders.filter(o=>o.status==="expired").length;
  const revenue=done.concat(act).reduce((s,o)=>s+o.price,0);
  const closedTotal=done.length+noshow;
  const fill=closedTotal?Math.round(done.length/closedTotal*100):null;
  const leftNow=boxes.reduce((s,b)=>s+b.qty_left,0);
  $("#pStats").innerHTML=[
    [money(revenue),"выручка с боксов"],[done.length+act.length,plural(done.length+act.length,["продажа","продажи","продаж"])],
    [fill===null?"—":fill+"%","выкуп (забрали)"],[leftNow,plural(leftNow,["бокс","бокса","боксов"])+" в продаже"],
  ].map(([v,l])=>`<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("");
  $("#pBoxes").innerHTML=boxes.length?boxes.map(b=>`<div class="lrow"><div style="font-size:1.2rem">${b.emoji}</div>
    <div class="g"><b>${esc(b.title||b.category_ru)}</b><div style="font-size:.76rem;color:var(--txt2)">${money(b.price)} · ${win(b.pickup_from,b.pickup_to)}</div></div>
    <span class="tag ${b.qty_left>0?"t-issued":"t-expired"}">${b.qty_left}/${b.qty_total}</span>
    <button class="linkbtn" data-act="editBox" data-a1="${esc(b.id)}" title="Редактировать">✏️</button>
    <button class="linkbtn" data-act="closeBox" data-a1="${esc(b.id)}" data-a2="${esc(b.title||b.category_ru)}" title="Снять с продажи" style="color:var(--red)">✕</button>
    </div>`).join(""):'<p class="empty">Боксов пока нет.</p>';
  $("#pOrders").innerHTML=orders.length?orders.map(o=>orderRow(o)).join(""):'<p class="empty">Броней пока нет.</p>';
  loadDailyStats(pid);
  loadStaff(pid);
}
async function loadDailyStats(pid){
  const box=$("#pDaily"); if(!box)return;
  let rows=[]; try{rows=await get(`/partners/${pid}/daily-stats?days=30`);}catch(e){}
  if(!rows.length){box.innerHTML='<p class="empty">Данных пока нет.</p>';return;}
  const totalRevenue=rows.reduce((s,r)=>s+r.revenue,0);
  const totalOrders=rows.reduce((s,r)=>s+r.orders_count,0);
  box.innerHTML=`<div class="stat" style="margin-bottom:.6rem"><b>${money(totalRevenue)}</b><span>выручка за ${rows.length} ${plural(rows.length,["день","дня","дней"])} (${totalOrders} ${plural(totalOrders,["заказ","заказа","заказов"])})</span></div>`
    +barChart(rows.map(r=>[r.day,r.revenue]));
}
/* ============ КАБИНЕТ ПАРТНЁРА: персонал (только владелец) ============ */
/* STAFF_ROLE_RU объявлена ниже (в блоке приглашений) — переиспользуем её. */
async function loadStaff(pid){
  const card=$("#pStaffCard"); if(!card)return;
  let rows;
  try{ rows=await get(`/partners/${pid}/staff`); }
  catch(e){ card.classList.add("hidden"); return; }   // не владелец → карточки нет
  card.classList.remove("hidden");
  window.__staffPid=pid;
  const list=$("#pStaff");
  list.innerHTML=rows.map(u=>{
    const owner=u.partner_role==="owner";
    const next=u.partner_role==="manager"?"cashier":"manager";
    return `<div class="lrow">
      <div class="g"><b>${esc(u.email)}</b>
        <div style="font-size:.76rem;color:var(--txt2)">${STAFF_ROLE_RU[u.partner_role]||esc(u.partner_role||"")}</div></div>
      <span class="tag ${u.is_active?"t-issued":"t-expired"}">${u.is_active?"активен":"отключён"}</span>
      ${owner?"":`<button class="linkbtn" data-act="staffRole" data-a1="${esc(u.id)}" data-a2="${next}" title="Сделать ${STAFF_ROLE_RU[next]}">${u.partner_role==="manager"?"↓ в кассиры":"↑ в менеджеры"}</button>
      <button class="linkbtn" data-act="staffActive" data-a1="${esc(u.id)}" data-a2="${u.is_active?"0":"1"}" style="color:${u.is_active?"var(--red)":"var(--green)"}">${u.is_active?"Отключить":"Вернуть"}</button>`}
    </div>`;
  }).join("")||'<p class="empty">Пока только вы.</p>';
  const btn=$("#stInvite");
  btn.onclick=async()=>{
    const email=$("#stEmail").value.trim(), role=$("#stRole").value;
    if(!email){toast("Укажите email",true);return;}
    btn.disabled=true;btn.textContent="Создаём…";
    try{
      const r=await post(`/partners/${pid}/staff-invitations`,{email,partner_role:role});
      $("#stResult").innerHTML=`<b style="color:var(--green)">Ссылка готова</b> — отправьте сотруднику (одноразовая, 7 дней):
        <div style="display:flex;gap:.4rem;margin-top:.35rem">
          <input id="stUrl" readonly value="${esc(r.invite_url)}" style="flex:1;font-size:.78rem" />
          <button class="btn sec" id="stCopy" style="width:auto;padding:.4rem .8rem">Копировать</button>
        </div>`;
      $("#stCopy").onclick=async()=>{try{await navigator.clipboard.writeText(r.invite_url);toast("Скопировано 🔗");}catch(e){$("#stUrl").select();}};
      $("#stEmail").value="";
    }catch(e){toast(e.message,true);}
    btn.disabled=false;btn.textContent="Пригласить в заведение";
  };
}
window.staffSetRole=async(id,role)=>{
  try{ await api("PATCH",`/partners/${window.__staffPid}/staff/${id}`,{partner_role:role});
    toast("Роль обновлена"); loadStaff(window.__staffPid);
  }catch(e){ toast(e.message,true); }
};
window.staffSetActive=async(id,active)=>{
  try{ await post(`/partners/${window.__staffPid}/staff/${id}/active?active=${active?"true":"false"}`,{});
    toast(active?"Сотрудник возвращён":"Сотрудник отключён — сессии разорваны"); loadStaff(window.__staffPid);
  }catch(e){ toast(e.message,true); }
};
function orderRow(o,admin=false){
  return `<div class="lrow"><div style="font-size:1.2rem">${o.emoji}</div>
    <div class="g"><b>${esc(o.code)}</b> · ${esc(o.user_name)} <span style="color:var(--txt2)">${esc(o.user_phone)}</span>
      <div style="font-size:.76rem;color:var(--txt2)">${admin?esc(o.partner_name)+" · ":""}${money(o.price)} · ${win(o.pickup_from,o.pickup_to)}</div></div>
    <span class="tag t-${o.status}">${STATUS_RU[o.status]}</span>
    ${admin&&(o.status==="paid")?`<button class="btn sec" style="width:auto;padding:.3rem .6rem;font-size:.74rem" data-act="refund" data-a1="${o.id}">Возврат</button>`:""}</div>`;
}
$("#boxForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const hours=Math.max(1,+$("#bHours").value||4);
  const now=new Date(), to=new Date(now.getTime()+hours*3600*1000);
  const body={partner_id:curPartner(),category:$("#bCat").value,title:$("#bTitle").value.trim(),
    price:+$("#bPrice").value,value_est:+$("#bValue").value,qty:+$("#bQty").value,
    pickup_from:now.toISOString(),pickup_to:to.toISOString(),description:$("#bDesc").value.trim()};
  if(!(body.price>=100&&body.price<=50000)){toast("Цена бокса — от 100 до 50 000 ₸",true);return;}
  if(body.value_est<body.price){toast("Ценность внутри должна быть не ниже цены",true);return;}
  if(!(body.qty>=1&&body.qty<=50)){toast("Количество — от 1 до 50",true);return;}
  try{await post("/boxes",body);toast("Бокс опубликован ✓");e.target.reset();$("#bPrice").value=990;$("#bValue").value=2600;$("#bQty").value=5;$("#bHours").value=4;loadPartnerData();}
  catch(err){toast(err.message,true);}
});
function tplBody(){return {partner_id:curPartner(),category:$("#bCat").value,title:$("#bTitle").value.trim()||"Вечерний бокс",
  price:+$("#bPrice").value,value_est:+$("#bValue").value,qty:+$("#bQty").value,
  hours:Math.max(1,Math.min(12,+$("#bHours").value||4)),description:$("#bDesc").value.trim()};}
$("#bSaveTpl").onclick=async()=>{
  const b=tplBody();
  if(b.value_est<b.price){toast("Ценность внутри должна быть не ниже цены",true);return;}
  try{await post(`/partners/${curPartner()}/templates`,b);toast("Шаблон сохранён 💾");renderTemplates();}
  catch(e){toast(e.message,true);}
};
window.publishTpl=async id=>{
  try{await post(`/partners/${curPartner()}/templates/${id}/publish`);toast("Бокс опубликован из шаблона ✓");loadPartnerData();}
  catch(e){toast(e.message,true);}
};
window.delTpl=async id=>{
  if(!confirm("Удалить шаблон?"))return;
  try{await del(`/partners/${curPartner()}/templates/${id}`);toast("Шаблон удалён");renderTemplates();}
  catch(e){toast(e.message,true);}
};
async function renderTemplates(){
  const el=$("#pTemplates");if(!el)return;
  let t=[];try{t=await get(`/partners/${curPartner()}/templates`);}catch(e){}
  if(!t.length){el.innerHTML='<span style="color:var(--txt2)">Пока нет. Заполни форму и нажми «Сохранить как шаблон» — потом публикуй одной кнопкой.</span>';return;}
  el.innerHTML=t.map(x=>`<div style="display:flex;align-items:center;gap:.5rem;padding:.4rem 0;border-bottom:1px solid var(--line)">
    <div style="flex:1"><b>${esc(x.title)}</b> · ${money(x.price)} <span style="color:var(--txt2)">(${x.qty} шт, до +${x.hours}ч)</span></div>
    <button class="btn" style="width:auto;padding:.3rem .7rem;font-size:.78rem" data-act="publishTpl" data-a1="${x.id}">Опубликовать</button>
    <button class="linkbtn" data-act="delTpl" data-a1="${x.id}">✕</button></div>`).join("");
}
$("#bAiBtn").onclick=async()=>{
  const notes=$("#bDesc").value.trim();
  if(notes.length<2){toast("Сначала напиши черновик — хотя бы пару слов",true);return;}
  const btn=$("#bAiBtn"), old=btn.textContent; btn.disabled=true; btn.textContent="Генерирую…";
  try{
    const r=await post("/ai/describe-box",{category:$("#bCat").value,notes});
    $("#bDesc").value=r.description;
    toast(r.ai?"Описание улучшено ИИ ✨":"Описание собрано по шаблону (демо-режим без AI-ключа)");
  }catch(e){toast(e.message,true);}
  btn.disabled=false; btn.textContent=old;
};
$("#redeemCode").addEventListener("input",e=>{e.target.value=e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g,"");});
$("#redeemBtn").onclick=async()=>{
  const code=$("#redeemCode").value.trim();if(!code){toast("Введите код",true);return;}
  try{const r=await post("/redeem",{code});
    $("#redeemRes").innerHTML=`<span class="tag ${r.ok?"t-issued":"t-expired"}">${r.ok?"✓ ":"✕ "}${esc(r.message)}</span>`+
      (r.order?` <span style="color:var(--txt2)">${esc(r.order.partner_name)} · ${money(r.order.price)}</span>`:"");
    if(r.ok){toast("Выдано ✓");loadPartnerData();}
  }catch(e){toast(e.message,true);}
};
/* QR-сканер камерой (html5-qrcode подгружается лениво, только при первом клике) */
let _scanner=null;
function loadScript(src){return new Promise((res,rej)=>{const s=document.createElement("script");s.src=src;s.onload=res;s.onerror=rej;document.head.appendChild(s);});}
$("#scanBtn").onclick=async()=>{
  const box=$("#scanBox");
  if(_scanner){try{await _scanner.stop();}catch(e){} _scanner=null; box.classList.add("hidden"); box.innerHTML=""; $("#scanBtn").textContent="📷 Сканировать QR камерой"; return;}
  try{ if(typeof Html5Qrcode==="undefined") await loadScript("https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"); }
  catch(e){toast("Не удалось загрузить сканер",true);return;}
  box.classList.remove("hidden"); box.innerHTML='<div id="qrReader" style="width:100%"></div>';
  $("#scanBtn").textContent="✕ Остановить сканер";
  _scanner=new Html5Qrcode("qrReader");
  try{
    await _scanner.start({facingMode:"environment"},{fps:10,qrbox:220},async decoded=>{
      const code=(decoded||"").trim().toUpperCase();
      if(!/^YM-/.test(code))return;                       // игнор посторонних QR
      try{await _scanner.stop();}catch(e){} _scanner=null;
      box.classList.add("hidden"); box.innerHTML=""; $("#scanBtn").textContent="📷 Сканировать QR камерой";
      $("#redeemCode").value=code; $("#redeemBtn").click();
    });
  }catch(e){toast("Нет доступа к камере",true);box.classList.add("hidden");$("#scanBtn").textContent="📷 Сканировать QR камерой";_scanner=null;}
};

