/* ============ КАБИНЕТ ПАРТНЁРА: правка и снятие бокса ============ */
window.editBoxForm=async id=>{
  let b; try{ b=await get("/boxes/"+id); }catch(e){ toast(e.message,true); return; }
  const dt=v=>{try{const d=new Date(v);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}catch(e){return "";}};
  showModal(`<div class="mc">
    <h3>Редактировать бокс</h3>
    <label>Название <input id="ebTitle" value="${esc(b.title||"")}" /></label>
    <label>Что внутри <textarea id="ebDesc" rows="2">${esc(b.description||"")}</textarea></label>
    <div class="frow">
      <label>Цена, ₸ <input id="ebPrice" type="number" min="100" value="${b.price}" /></label>
      <label>Ценность, ₸ <input id="ebValue" type="number" min="100" value="${b.value_est}" /></label>
    </div>
    <div class="frow">
      <label>Всего боксов <input id="ebQty" type="number" min="1" max="50" value="${b.qty_total}" /></label>
      <label>Осталось <input value="${b.qty_left}" disabled /></label>
    </div>
    <div class="frow">
      <label>Выдача с <input id="ebFrom" type="datetime-local" value="${dt(b.pickup_from)}" /></label>
      <label>до <input id="ebTo" type="datetime-local" value="${dt(b.pickup_to)}" /></label>
    </div>
    <button class="btn" id="ebSave" style="margin-top:.7rem">Сохранить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#ebSave").onclick=async()=>{
    const btn=$("#ebSave"); btn.disabled=true; btn.textContent="Сохраняем…";
    const iso=v=>v?new Date(v).toISOString():undefined;
    try{
      await api("PATCH","/boxes/"+id,{title:$("#ebTitle").value.trim(),
        description:$("#ebDesc").value.trim(),price:+$("#ebPrice").value,
        value_est:+$("#ebValue").value,qty_total:+$("#ebQty").value,
        pickup_from:iso($("#ebFrom").value),pickup_to:iso($("#ebTo").value)});
      closeModal(); toast("Бокс обновлён ✓"); loadPartnerData();
    }catch(e){ toast(e.message,true); btn.disabled=false; btn.textContent="Сохранить"; }
  };
};
window.closeBoxConfirm=(id,title)=>{
  showModal(`<div class="mc">
    <h3>Снять с продажи?</h3>
    <p style="font-size:.86rem;color:var(--txt2);margin:.3rem 0 .9rem">«${esc(title||"Бокс")}» исчезнет из витрины. Уже оплаченные заказы останутся — их нужно выдать.</p>
    <button class="btn" id="cbYes" style="background:var(--red);color:#fff">Снять с продажи</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#cbYes").onclick=async()=>{
    try{ await del("/boxes/"+id); closeModal(); toast("Бокс снят с продажи"); loadPartnerData(); }
    catch(e){ toast(e.message,true); }
  };
};

/* CSV качаем через fetch с Bearer-токеном: обычная ссылка его не отправит → 401 */
window.downloadCsv=async(url,filename)=>{
  const a=account();
  try{
    const base=(typeof API_BASE!=="undefined"?API_BASE:"");
    const r=await fetch(base+url,{headers:a&&a.token?{"Authorization":"Bearer "+a.token}:{}});
    if(!r.ok)throw new Error(r.status===401||r.status===403?"Нет доступа":"Не удалось выгрузить");
    const blob=await r.blob(), link=document.createElement("a");
    link.href=URL.createObjectURL(blob); link.download=filename;
    document.body.appendChild(link); link.click(); link.remove();
    URL.revokeObjectURL(link.href); toast("Файл скачан ⬇");
  }catch(e){ toast(e.message,true); }
};

