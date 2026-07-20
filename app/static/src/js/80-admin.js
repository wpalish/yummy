/* ============ АДМИН ============ */
/* ---- мини-визуализация на inline-SVG (идея из Plotly Dash, но без зависимостей) ---- */
function svgDonut(segs){
  const r=52,cx=64,cy=64,C=2*Math.PI*r,total=segs.reduce((s,x)=>s+x.value,0);
  if(!total)return `<svg viewBox="0 0 128 128" style="width:130px;height:130px;display:block;margin:0 auto"><circle cx="64" cy="64" r="52" fill="none" stroke="var(--cream-d)" stroke-width="18"/><text x="64" y="68" text-anchor="middle" font-size="11" fill="#7E6A5A">нет данных</text></svg>`;
  let acc=0;
  const arcs=segs.filter(s=>s.value>0).map(s=>{const f=s.value/total,dash=f*C,el=`<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${s.color}" stroke-width="18" stroke-dasharray="${dash} ${C-dash}" stroke-dashoffset="${-acc*C}" transform="rotate(-90 ${cx} ${cy})"/>`;acc+=f;return el;}).join("");
  return `<svg viewBox="0 0 128 128" style="width:130px;height:130px;display:block;margin:0 auto">${arcs}<text x="64" y="60" text-anchor="middle" font-size="21" font-weight="800" fill="#653624">${total}</text><text x="64" y="76" text-anchor="middle" font-size="9" fill="#7E6A5A">заказов</text></svg>`;
}
function svgGauge(pct){
  pct=Math.max(0,Math.min(100,pct||0));const r=54,cx=64,cy=66,C=Math.PI*r,f=pct/100;
  const arc=(color,len,cap)=>`<path d="M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}" fill="none" stroke="${color}" stroke-width="14"${cap?' stroke-linecap="round"':''} stroke-dasharray="${len} ${C*2}"/>`;
  return `<svg viewBox="0 0 128 84" style="width:100%;max-width:200px;display:block;margin:.3rem auto 0">${arc('#F0E8D4',C,false)}${arc('#3E9142',f*C,true)}<text x="64" y="58" text-anchor="middle" font-size="23" font-weight="800" fill="#653624">${Math.round(pct)}%</text><text x="64" y="76" text-anchor="middle" font-size="9" fill="#7E6A5A">выкуплено</text></svg>`;
}
function barChart(rows){ // rows: [[name,value]]
  const max=Math.max(1,...rows.map(r=>r[1]));
  return rows.map(([n,v])=>`<div class="brow"><span class="nm">${esc(n)}</span><span class="bar"><i style="width:${Math.round(v/max*100)}%"></i></span><span class="val">${money(v)}</span></div>`).join("")||'<p class="empty" style="padding:.6rem">нет данных</p>';
}
/* Приглашения: единственный вход в партнёрку (покупатель его не видит) */
function ivToggleFields(){
  const owner=$("#ivRole").value==="owner";
  $("#ivOwnerFields").classList.toggle("hidden",!owner);
  $("#ivPartnerField").classList.toggle("hidden",owner);
}
async function loadInvites(){
  const sel=$("#ivPartner"); if(!sel)return;
  $("#ivRole").onchange=ivToggleFields; ivToggleFields();
  try{const ps=await get("/partners");
    sel.innerHTML=ps.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  }catch(e){}
  $("#ivCreate").onclick=async()=>{
    const b=$("#ivCreate"), role=$("#ivRole").value;
    const body={email:$("#ivEmail").value.trim(),partner_role:role};
    if(role==="owner"){body.brand_name=$("#ivBrand").value.trim();body.address=$("#ivAddr").value.trim();}
    else body.partner_id=$("#ivPartner").value;
    b.disabled=true;b.textContent="Создаём…";
    try{
      const r=await post("/admin/staff-invitations",body);
      $("#ivResult").innerHTML=`<b style="color:var(--green)">Ссылка готова</b> — отправьте её заведению (одноразовая, 7 дней):
        <div style="display:flex;gap:.4rem;margin-top:.35rem">
          <input id="ivUrl" readonly value="${esc(r.invite_url)}" style="flex:1;font-size:.78rem" />
          <button class="btn sec" id="ivCopy" style="width:auto;padding:.4rem .8rem">Копировать</button>
        </div>`;
      $("#ivCopy").onclick=async()=>{try{await navigator.clipboard.writeText(r.invite_url);toast("Скопировано 🔗");}catch(e){$("#ivUrl").select();}};
      $("#ivEmail").value="";
    }catch(e){toast(e.message,true);}
    b.disabled=false;b.textContent="Создать ссылку-приглашение";
  };
}
