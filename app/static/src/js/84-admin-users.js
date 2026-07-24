/* ============ АДМИН: пользователи, блокировка, сессии ============ */
const ROLE_BADGE={admin:"админ",partner:"заведение",customer:"покупатель"};
async function loadUsers(){
  const el=$("#aUsers"); if(!el)return;
  let rows=[];
  try{ rows=await get("/admin/users?limit=100"); }catch(e){ el.innerHTML='<p class="sub">Не удалось загрузить.</p>'; return; }
  if(!rows.length){ el.innerHTML='<p class="sub">Пользователей пока нет.</p>'; return; }
  el.innerHTML=rows.map(u=>`
    <div class="lrow">
      <div class="g"><b>${esc(u.email)}</b>
        <div style="font-size:.76rem;color:var(--txt2)">${ROLE_BADGE[u.role]||esc(u.role)}${u.partner_role?" · "+esc(u.partner_role):""}${u.brand_name?" · "+esc(u.brand_name):""}</div>
      </div>
      <span class="tag ${u.is_active?"t-issued":"t-expired"}">${u.is_active?"активен":"заблокирован"}</span>
      <button class="linkbtn" data-act="revokeUser" data-a1="${esc(u.id)}" title="Разлогинить со всех устройств">🚪</button>
      <button class="linkbtn" data-act="blockUser" data-a1="${esc(u.id)}" data-a2="${u.is_active?"0":"1"}" style="color:${u.is_active?"var(--red)":"var(--green)"}">${u.is_active?"Заблокировать":"Разблокировать"}</button>
    </div>`).join("");
}
window.toggleUserBlock=async(id,active)=>{
  try{ await post(`/admin/users/${id}/block?active=${active?"true":"false"}`,{});
    toast(active?"Разблокирован":"Заблокирован — сессии разорваны"); loadUsers();
  }catch(e){ toast(e.message,true); }
};
window.revokeUserSessions=async id=>{
  try{ await post(`/admin/users/${id}/revoke-sessions`,{}); toast("Разлогинен со всех устройств"); }
  catch(e){ toast(e.message,true); }
};

/* 2FA (TOTP): включение с QR, выключение по коду.
   Слоты .totp-slot: и в админке (#aTotp), и в кабинете владельца (#pTotp) —
   оба обновляются одним статусом. */
async function loadTotp(){
  const els=[...document.querySelectorAll(".totp-slot")]; if(!els.length)return;
  let st={enabled:false};
  try{ st=await get("/auth/totp/status"); }
  catch(e){ els.forEach(el=>el.innerHTML='<p class="sub">Требуется вход.</p>'); return; }
  const html=st.enabled
    ?'<span class="tag t-issued">2FA включена</span> <button class="linkbtn" data-act="totpOff">Выключить…</button>'
    :'<span class="tag t-expired">2FA выключена</span> <button class="btn sec" data-act="totpOn" style="width:auto;padding:.4rem .9rem;margin-left:.5rem">Включить 2FA</button>';
  els.forEach(el=>el.innerHTML=html);
}
window.totpOn=async()=>{
  let s; try{ s=await post("/auth/totp/setup",{}); }catch(e){ toast(e.message,true); return; }
  showModal(`<div class="mc"><h3>Включение 2FA</h3>
    <p class="sub">1. Отсканируйте QR в Google Authenticator / 1Password.<br>2. Введите код из приложения.</p>
    <div style="background:#fff;padding:.6rem;border-radius:12px;max-width:220px;margin:.4rem auto">${s.qr_svg}</div>
    <p style="font-size:.72rem;color:var(--txt2);word-break:break-all">Секрет вручную: <code>${esc(s.secret)}</code></p>
    <label>Код <input id="teCode" inputmode="numeric" maxlength="6" placeholder="123456" autocomplete="off" /><span class="ferr" id="teErr"></span></label>
    <button class="btn" id="teSave" style="margin-top:.5rem">Подтвердить и включить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button></div>`);
  $("#teSave").onclick=async()=>{
    const b=$("#teSave"); b.disabled=true;
    try{ await post("/auth/totp/enable",{secret:s.secret,code:$("#teCode").value.trim()});
      closeModal(); toast("2FA включена 🔐"); loadTotp(); }
    catch(e){ $("#teErr").textContent=e.message; b.disabled=false; }
  };
};
window.totpOff=()=>{
  showModal(`<div class="mc"><h3>Выключить 2FA</h3>
    <label>Текущий код из приложения <input id="tdCode" inputmode="numeric" maxlength="6" autocomplete="off" /><span class="ferr" id="tdErr"></span></label>
    <button class="btn" id="tdSave" style="margin-top:.5rem;background:var(--red)">Выключить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button></div>`);
  $("#tdSave").onclick=async()=>{
    const b=$("#tdSave"); b.disabled=true;
    try{ await post("/auth/totp/disable",{code:$("#tdCode").value.trim()});
      closeModal(); toast("2FA выключена"); loadTotp(); }
    catch(e){ $("#tdErr").textContent=e.message; b.disabled=false; }
  };
};

/* Аудит-журнал: персистентный (БД, 90 дней), IP — хешем */
async function loadAudit(){
  const el=$("#aAudit"); if(!el)return;
  let rows=[];
  try{ rows=await get("/admin/audit?limit=100"); }
  catch(e){ el.innerHTML='<p class="sub">Не удалось загрузить.</p>'; return; }
  el.innerHTML=rows.length?rows.map(r=>
    `<div style="padding:.15rem 0;border-bottom:1px solid var(--line)"><span style="color:var(--txt2)">${esc((r.ts||"").slice(0,19).replace("T"," "))}</span> ${esc(r.event)}</div>`
  ).join(""):'<p class="sub">Событий пока нет.</p>';
}

/* «Кого зовут» — спрос на заведения с карты (очередь на подключение) */
async function loadVenueInterest(){
  const el=$("#aVenueInterest"); if(!el)return;
  let rows=[];
  try{ rows=await get("/admin/venue-interest?limit=20"); }catch(e){ el.innerHTML='<p class="sub">Не удалось загрузить.</p>'; return; }
  if(!rows.length){ el.innerHTML='<p class="sub">Пока никто не голосовал. Кнопка «Хочу боксы отсюда» — в карточке заведения на вкладке «Рядом».</p>'; return; }
  const max=rows[0].votes||1;
  el.innerHTML=rows.map((r,i)=>`
    <div class="lrow">
      <div style="font-size:1rem;width:1.6rem;text-align:center;font-weight:800;color:var(--txt2)">${i+1}</div>
      <div class="g"><b>${esc(r.name)}</b>
        <div style="font-size:.76rem;color:var(--txt2)">${esc(r.address||"")}${r.district?" · "+esc(r.district):""}</div>
        <div style="height:5px;border-radius:99px;background:var(--border);margin-top:.3rem;overflow:hidden">
          <div style="height:100%;width:${Math.round(r.votes/max*100)}%;background:var(--brown)"></div></div>
      </div>
      <span class="pill" style="white-space:nowrap">${r.votes} ${plural(r.votes,["голос","голоса","голосов"])}</span>
    </div>`).join("");
}
async function loadAdmin(){
  let s={},orders=[];
  loadInvites(); loadVenueInterest(); loadUsers(); loadAudit(); loadTotp();
  try{s=await get("/admin/stats");}catch(e){}
  try{orders=await get("/admin/orders?limit=100");}catch(e){}
  window.__ordOffset=orders.length;
  {const mb=$("#aMoreOrders"); if(mb){ mb.classList.toggle("hidden",orders.length<100);
    mb.onclick=async()=>{
      try{
        const more=await get(`/admin/orders?limit=100&offset=${window.__ordOffset}`);
        window.__ordOffset+=more.length;
        $("#aOrders").insertAdjacentHTML("beforeend",more.map(o=>orderRow(o,true)).join(""));
        if(more.length<100)mb.classList.add("hidden");
      }catch(e){toast(e.message,true);}
    };}}
  $("#aStats").innerHTML=[
    [money(s.gmv||0),"GMV (оборот)"],[s.orders_total||0,"заказов"],
    [(s.fill_rate||0)+"%","выкуплено (fill rate)"],[s.no_show||0,"не забрали (no-show)"],
    [s.issued||0,"выдано"],[s.active||0,"активных"],[s.refunds||0,"возвратов"],[(s.gmv? Math.round(s.gmv*0.1):0)+" ₸","take 10% (прогноз)"],
  ].map(([v,l])=>`<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("");
  // графики из заказов
  const cnt={paid:0,issued:0,expired:0,refunded:0,cancelled:0};
  const byPartner={};
  orders.forEach(o=>{cnt[o.status]=(cnt[o.status]||0)+1;
    if(o.status==="issued"||o.status==="paid")byPartner[o.partner_name]=(byPartner[o.partner_name]||0)+o.price;});
  const statusSegs=[
    {label:"выдано",value:cnt.issued,color:"#3E9142"},
    {label:"активные",value:cnt.paid,color:"#D08641"},
    {label:"не забрали",value:cnt.expired,color:"#B9A88F"},
    {label:"возвраты",value:(cnt.refunded||0)+(cnt.cancelled||0),color:"#E84855"},
  ];
  const topPartners=Object.entries(byPartner).sort((a,b)=>b[1]-a[1]).slice(0,5);
  $("#aCharts").innerHTML=`
    <div class="chart"><h4>Заказы по статусу</h4>${svgDonut(statusSegs)}
      <div class="leg">${statusSegs.map(s=>`<span><i style="background:${s.color}"></i>${s.label} · ${s.value}</span>`).join("")}</div></div>
    <div class="chart"><h4>Выкуп боксов</h4>${svgGauge(s.fill_rate||0)}
      <div class="leg" style="justify-content:center">${s.issued||0} выдано · ${s.no_show||0} не забрали</div></div>
    <div class="chart"><h4>Выручка по заведениям · топ-5</h4>${barChart(topPartners)}</div>`;
  $("#aOrders").innerHTML=orders.length?orders.map(o=>orderRow(o,true)).join(""):'<p class="empty">Заказов нет.</p>';
  renderPayments();
}
async function renderPayments(){
  const el=$("#aPayments");if(!el)return;
  let ps=[],accs=[],invs=[];
  try{[ps,accs,invs]=await Promise.all([get("/partners"),
    get("/admin/payment-accounts").catch(()=>[]),
    get("/admin/commission-invoices").catch(()=>[])]);}catch(e){}
  const byPid=Object.fromEntries(accs.map(a=>[a.partner_id,a]));
  el.innerHTML=ps.map(p=>{
    const a=byPid[p.id]||{};
    const st=a.status||"none";
    const badge={active:'<span class="tag t-issued">активен</span>',pending:'<span class="tag t-paid">подключён</span>',
      suspended:'<span class="tag t-expired">приостановлен</span>',none:'<span class="tag t-expired">нет</span>'}[st]||st;
    const rate=a.rate_bps!=null?(a.rate_bps/100)+"%":"—";
    const owed=a.owed_tenge!=null?money(a.owed_tenge):"—";
    const ref=a.merchant_masked?`<span title="${a.encrypted?"реквизит зашифрован в БД":"легаси-плейнтекст"}">${a.encrypted?"🔒":"⚠️"} ${esc(a.merchant_masked)}</span>`:"";
    return `<div style="padding:.5rem 0;border-bottom:1px solid var(--line)">
      <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
        <b style="flex:1;min-width:120px">${esc(p.name)}</b> ${badge} ${ref}
        <span style="color:var(--txt2)">комиссия ${rate} · долг ${owed}</span></div>
      <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.35rem">
        ${st==="none"?`<button class="linkbtn" data-act="connectPay" data-a1="${p.id}">Подключить Kaspi-мерчант</button>`:""}
        ${(st==="pending"||st==="suspended")?`<button class="linkbtn" data-act="activatePay" data-a1="${p.id}">Активировать приём</button>`:""}
        ${st==="active"?`<button class="linkbtn" data-act="suspendPay" data-a1="${p.id}" style="color:var(--red)">Приостановить</button>`:""}
        ${st!=="none"?`<button class="linkbtn" data-act="rotatePay" data-a1="${p.id}" title="Новый webhook-id; опционально новый реквизит">Ротация</button>`:""}
        ${a.owed_minor>0?`<button class="linkbtn" data-act="makeInvoice" data-a1="${p.id}">Выставить счёт (${money(a.owed_tenge)})</button>`:""}
        <button class="linkbtn" data-act="setRate" data-a1="${p.id}">Ставка комиссии</button>
      </div></div>`;
  }).join("")+renderInvoices(invs,ps);
}
function renderInvoices(invs,ps){
  if(!invs.length)return "";
  const pname=Object.fromEntries(ps.map(p=>[p.id,p.name]));
  const st={open:'<span class="tag t-paid">открыт</span>',paid:'<span class="tag t-issued">оплачен</span>',void:'<span class="tag t-expired">аннулирован</span>'};
  return `<h4 style="margin:.9rem 0 .3rem">Счета за комиссию</h4>`+invs.map(i=>`
    <div class="lrow"><div class="g"><b>${esc(pname[i.partner_id]||i.partner_id)}</b>
      <div style="font-size:.76rem;color:var(--txt2)">${money(Math.floor(i.total_minor/100))} · ${i.entries_count} зак. · ${(i.created_at||"").slice(0,10)}</div></div>
      ${st[i.status]||esc(i.status)}
      ${i.status==="open"?`<button class="linkbtn" data-act="invoicePaid" data-a1="${esc(i.id)}">Оплачен</button>
      <button class="linkbtn" data-act="invoiceVoid" data-a1="${esc(i.id)}" style="color:var(--red)">Аннулировать</button>`:""}
    </div>`).join("");
}
window.suspendPay=async id=>{if(!confirm("Приостановить приём платежей? Партнёр не сможет продавать платные боксы."))return;
  try{await post(`/partners/${id}/payment-account/suspend`,{});toast("Платежи приостановлены");renderPayments();}catch(e){toast(e.message,true);}};
window.rotatePay=id=>{
  showModal(`<div class="mc"><h3>Ротация платёжного аккаунта</h3>
    <p class="sub" style="margin:.2rem 0 .6rem">Webhook-id сменится в любом случае. Реквизит — только если заполнить поле.</p>
    <label>Новый merchant reference (необязательно)
      <input id="rtRef" autocomplete="off" placeholder="пусто — только webhook-id" maxlength="120" /></label>
    <button class="btn" id="rtSave" style="margin-top:.6rem">Выполнить ротацию</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button></div>`);
  $("#rtSave").onclick=async()=>{
    const ref=$("#rtRef").value.trim();
    const b=$("#rtSave"); b.disabled=true;
    try{await post(`/partners/${id}/payment-account/rotate`,ref?{provider:"kaspi",merchant_reference:ref}:undefined);
      closeModal();toast("Ротация выполнена 🔄");renderPayments();}
    catch(e){toast(e.message,true);b.disabled=false;}
  };
};
window.makeInvoice=async id=>{if(!confirm("Выставить счёт на всю накопленную комиссию?"))return;
  try{const inv=await post(`/partners/${id}/commission-invoice`,{});
    toast(`Счёт на ${money(Math.floor(inv.total_minor/100))} выставлен`);renderPayments();}catch(e){toast(e.message,true);}};
window.invoicePaid=async id=>{try{await post(`/admin/commission-invoices/${id}/paid`,{});toast("Счёт закрыт ✓");renderPayments();}catch(e){toast(e.message,true);}};
window.invoiceVoid=async id=>{if(!confirm("Аннулировать счёт? Строки вернутся в пул и попадут в следующий."))return;
  try{await post(`/admin/commission-invoices/${id}/void`,{});toast("Счёт аннулирован");renderPayments();}catch(e){toast(e.message,true);}};
/* Модалки вместо prompt(): валидация, автозаполнение, нормальный вид на мобиле */
window.connectPay=id=>{
  showModal(`<div class="mc"><h3>Подключить Kaspi-мерчант</h3>
    <label>Merchant reference / ИИН точки
      <input id="cpRef" autocomplete="off" placeholder="KZ-XXXX или ИИН" minlength="2" maxlength="120" />
      <span class="ferr" id="cpErr"></span></label>
    <button class="btn" id="cpSave" style="margin-top:.6rem">Подключить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button></div>`);
  $("#cpRef").focus();
  $("#cpSave").onclick=async()=>{
    const ref=$("#cpRef").value.trim();
    if(ref.length<2){$("#cpErr").textContent="Минимум 2 символа";return;}
    const b=$("#cpSave"); b.disabled=true;
    try{await post(`/partners/${id}/payment-account`,{provider:"kaspi",merchant_reference:ref});
      closeModal();toast("Мерчант подключён 🔒");renderPayments();}
    catch(e){$("#cpErr").textContent=e.message;b.disabled=false;}
  };
};
window.activatePay=async id=>{if(!confirm("Активировать приём платежей? Партнёр сможет продавать платные боксы."))return;
  try{await post(`/partners/${id}/payment-account/activate`,{});toast("Приём платежей активен ✓");renderPayments();}catch(e){toast(e.message,true);}};
window.setRate=id=>{
  showModal(`<div class="mc"><h3>Ставка комиссии</h3>
    <label>Комиссия, % (0–50)
      <input id="crPct" type="number" min="0" max="50" step="0.5" value="10" />
      <span class="ferr" id="crErr"></span></label>
    <button class="btn" id="crSave" style="margin-top:.6rem">Сохранить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button></div>`);
  $("#crSave").onclick=async()=>{
    const bps=Math.round(parseFloat($("#crPct").value)*100);
    if(!(bps>=0&&bps<=5000)){$("#crErr").textContent="Допустимо 0–50%";return;}
    const b=$("#crSave"); b.disabled=true;
    try{await post(`/partners/${id}/commission-rule`,{rate_bps:bps});
      closeModal();toast("Ставка обновлена");renderPayments();}
    catch(e){$("#crErr").textContent=e.message;b.disabled=false;}
  };
};
window.refund=async id=>{try{await post("/admin/refund/"+id);toast("Возврат оформлен");loadAdmin();}catch(e){toast(e.message,true);}};

