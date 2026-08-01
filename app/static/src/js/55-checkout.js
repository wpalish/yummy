/* ============ ОФОРМЛЕНИЕ ЗАКАЗА ============ */
/* Отдельный экран вместо тесной модалки: способ оплаты, детали самовывоза
   с картой и сводка заказа. Способ оплаты — только тот, что реально работает
   (Kaspi через ApiPay либо демо-оплата пилота); чужие платёжные бренды
   (Visa/Mastercard/Google Pay) не рисуем — их у нас нет. */
let CK_BOX=null, ckMap=null;

window.checkoutBack=()=>switchView("store");
async function openCheckout(boxId){
  let b; try{ b=await get("/boxes/"+boxId); }catch(e){ toast(e.message,true); return; }
  CK_BOX=b; closeModal(); switchView("checkout"); renderCheckout();
}
function renderCheckout(){
  const b=CK_BOX; if(!b)return;
  const saving=Math.max(0,b.value_est-b.price);
  const acc=account()||{};
  $("#ckBody").innerHTML=`
    <div>
      <div class="ckc">
        <h3>Способ оплаты</h3>
        <div class="paym">
          ${b.pay_on_pickup?`<label><input type="radio" name="paym" value="pickup" checked>
            <span class="pay-l">💵 Оплата на месте при получении</span></label>`
          :APIPAY?`<label><input type="radio" name="paym" value="kaspi" checked>
            <span class="pay-l"><span class="kaspi">Kaspi</span> Счёт в приложении</span></label>`
          :`<label><input type="radio" name="paym" value="demo" checked>
            <span class="pay-l">🧪 Демо-оплата пилота</span></label>`}
        </div>
        <p style="font-size:.76rem;color:var(--txt2);margin:.7rem 0 0">
          ${b.pay_on_pickup?"Бокс закрепим за вами. Оплатите на кассе, когда придёте забирать."
          :APIPAY?"Счёт придёт в приложение Kaspi на ваш номер — подтвердите оплату там."
                  :"Пилот: оплата тестовая, деньги не списываются. В продакшене — Kaspi."}</p>
      </div>

      <div class="ckc ck-pickup">
        <h3>Детали самовывоза</h3>
        <div style="font-size:.92rem"><b>${esc(b.partner_name)}</b></div>
        <div style="font-size:.84rem;color:var(--txt2);margin:.15rem 0 .5rem">${esc(b.address)} · ${esc(b.district)}</div>
        <div class="row"><span>Время выдачи</span><b>${win(b.pickup_from,b.pickup_to)}</b></div>
        <div id="ckMap" class="ck-map"></div>
        <a href="${gisUrl(b.partner_name,b.address)}" target="_blank" rel="noopener"
          style="display:inline-block;margin-top:.6rem;font-size:.8rem;font-weight:700">🗺 Маршрут в 2ГИС →</a>
      </div>

      <div class="ckc">
        <h3>Ваши контакты</h3>
        <label>Имя <input id="ckName" placeholder="Как к вам обращаться" autocomplete="name" value="${esc(acc.name||"")}" /></label>
        <label>Телефон <input id="ckPhone" placeholder="+7 7XX XXX XX XX" autocomplete="tel" value="${esc(acc.phone||"")}" /></label>
        <span class="ferr" id="ckErr"></span>
        <button class="btn" id="ckPay" style="margin-top:.6rem">${b.pay_on_pickup?`Забронировать за ${money(b.price)}`:`Оплатить ${money(b.price)}`}</button>
      </div>
    </div>

    <div class="cksum">
      <div class="ckc">
        <h3>Ваш заказ</h3>
        <img class="ph" src="/static/img/${imgFor(b)}" alt="" loading="lazy">
        <div style="font-weight:800;color:var(--ink)">${esc(b.title||b.category_ru)}</div>
        <div style="font-size:.82rem;color:var(--txt2);margin-bottom:.7rem">${esc(b.partner_name)}</div>
        <div class="row"><span>Цена бокса</span><b>${money(b.price)}</b></div>
        <div class="row"><span>Обычная стоимость</span><s style="color:var(--txt2)">${money(b.value_est)}</s></div>
        <div class="row"><span>Экономия</span><span class="save">−${money(saving)} (−${b.discount}%)</span></div>
        <div class="ck-total"><span>Итого</span><b>${money(b.price)}</b></div>
        <p style="font-size:.74rem;color:var(--txt2);margin:.8rem 0 0">
          Сюрприз-бокс: точный состав может отличаться. Забрать нужно в окне самовывоза,
          иначе заказ сгорает. Если заведение не выдаст — полный возврат.</p>
      </div>
    </div>`;
  drawCkMap(b);
  $("#ckPay").onclick=payCheckout;
}
function drawCkMap(b){
  const el=$("#ckMap"); if(!el||typeof L==="undefined")return;
  const g=PARTNER_GEO[b.partner_id]; if(!g)return;         // координаты только у партнёра
  if(ckMap){ckMap.remove();ckMap=null;}
  ckMap=L.map(el,{zoomControl:false,scrollWheelZoom:false}).setView([g.lat,g.lng],15);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(ckMap);
  L.marker([g.lat,g.lng]).addTo(ckMap);
  setTimeout(()=>ckMap.invalidateSize(),120);
}
async function payCheckout(){
  const b=CK_BOX, name=$("#ckName").value.trim(), phone=$("#ckPhone").value.trim();
  if(!name||phone.length<5){$("#ckErr").textContent="Укажите имя и телефон";return;}
  const btn=$("#ckPay"); btn.disabled=true; btn.textContent="Оплата…";
  try{
    const res=await post("/orders",{box_id:b.id,user_name:name,user_phone:phone});
    saveCode(res.order.code);
    const a=account(); if(a&&a.role==="buyer"&&!a.phone){a.phone=phone;setAccount(a);}
    switchView("store");                 // витрину обновит loadStore, поверх — экран успеха
    successScreen(res);
  }catch(e){
    $("#ckErr").textContent=e.message; btn.disabled=false; btn.textContent="Оплатить "+money(b.price);
  }
}
