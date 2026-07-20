/* ============ МАГАЗИН ============ */
let ALL_BOXES=[];
const skCard=()=>'<div class="sk"><div class="a"></div><div class="b"></div><div class="c"></div></div>';
async function loadStore(){
  $("#cats").innerHTML=CATS.map(([id,l,ic])=>`<button class="cat${curCat===id?" on":""}" data-c="${id}" aria-pressed="${curCat===id}"><span class="ic">${ic}</span>${l}</button>`).join("");
  document.querySelectorAll("#cats .cat").forEach(c=>c.onclick=()=>{curCat=c.dataset.c;saveFilters();loadStore();});
  $("#boxes").innerHTML=skCard().repeat(6);
  let ds=[];try{ds=await get("/districts");}catch(e){}
  const hasFilters=curCat!=="all"||curDistrict!=="all"||curNow||curFav||curQuery;
  $("#districts").innerHTML=[`<button class="dist${curNow?" on":""}" data-now="1">⚡ Забрать сейчас</button>`,
      `<button class="dist${curFav?" on":""}" data-fav="1">♥ Любимые</button>`,
      `<button class="dist${curDistrict==="all"?" on":""}" data-d="all">Все районы</button>`]
    .concat(ds.map(d=>`<button class="dist${curDistrict===d?" on":""}" data-d="${esc(d)}">${esc(d)}</button>`))
    .concat(hasFilters?['<button class="dist" data-reset="1" style="color:var(--red)">✕ Сбросить</button>']:[]).join("");
  document.querySelectorAll("#districts .dist").forEach(c=>c.onclick=()=>{
    if(c.dataset.reset){curCat="all";curDistrict="all";curNow=false;curFav=false;curQuery="";["q","qm"].forEach(id=>{const e=$("#"+id);if(e)e.value="";});}
    else if(c.dataset.now){curNow=!curNow;}
    else if(c.dataset.fav){curFav=!curFav;}
    else curDistrict=c.dataset.d;
    saveFilters();loadStore();});
  try{ALL_BOXES=await get("/boxes?district=all");}catch(e){ALL_BOXES=[];}
  const totalLeft=ALL_BOXES.reduce((s,b)=>s+b.qty_left,0);
  $("#heroSub").textContent=totalLeft
    ?`${totalLeft} ${plural(totalLeft,["бокс доступен","бокса доступно","боксов доступно"])} к самовывозу сегодня вечером. Свежее, дешевле и без списаний.`
    :"Свежее, дешевле и без списаний.";
  renderBoxes();
  if(mapMode)renderMap();
  renderMyOrders();
  renderRecommendations();
}
async function renderRecommendations(){
  const wrap=$("#recoWrap");
  // демо — работает и без токена (по кодам в браузере); реальный бэкенд требует вход
  const demoMode=typeof API_BASE!=="undefined"&&API_BASE==="";
  const a=account();
  if(!demoMode&&!(a&&a.token)){wrap.classList.add("hidden");return;}
  let recs=[];
  try{recs=await get("/me/recommendations");}catch(e){wrap.classList.add("hidden");return;}
  if(!recs.length){wrap.classList.add("hidden");return;}
  $("#recoBoxes").innerHTML=recs.map(boxCard).join("");
  document.querySelectorAll("#recoBoxes .boxc").forEach(el=>el.onclick=()=>openBox(el.dataset.id));
  wrap.classList.remove("hidden");
}
function filtered(){
  let bs=ALL_BOXES.slice();
  if(curDistrict!=="all")bs=bs.filter(b=>b.district===curDistrict);
  if(curCat!=="all")bs=bs.filter(b=>b.category===curCat);
  if(curNow){const t=Date.now();bs=bs.filter(b=>Date.parse(b.pickup_from)<=t&&t<=Date.parse(b.pickup_to));}
  if(curFav){const f=favs();bs=bs.filter(b=>f.includes(b.partner_id));}
  if(curQuery)bs=bs.filter(b=>(b.title+" "+b.partner_name+" "+(b.description||"")+" "+b.category_ru).toLowerCase().includes(curQuery));
  // по умолчанию — «скоро закроется окно выдачи» выше (стимул забрать сейчас)
  bs.sort((a,b)=>Date.parse(a.pickup_to)-Date.parse(b.pickup_to));
  return bs;
}
function renderBoxes(){
  const bs=filtered();
  $("#listTitle").textContent=bs.length?`Боксы рядом (${bs.length})`:"Боксы рядом";
  $("#boxes").innerHTML=bs.length?bs.map(boxCard).join(""):'<p class="empty">Ничего не нашлось. Попробуй другой район или категорию 🌙</p>';
  document.querySelectorAll(".boxc").forEach(el=>el.onclick=()=>openBox(el.dataset.id));
}
const IMG={sweet:"sweet.jpg",bakery:"bakery.jpg",mixed:"mixed.jpg",snack:"snack.jpg"};
const IMG_ALT={sweet:"dessert.jpg",bakery:"bread.jpg"};
function imgFor(b){
  const t=(b.title||"").toLowerCase();
  if(t.includes("donut")||t.includes("пончик"))return "sweet.jpg";
  if(t.includes("dessert")||t.includes("десерт"))return "dessert.jpg";
  const alt=IMG_ALT[b.category];
  if(alt && (String(b.id).charCodeAt(String(b.id).length-1)&1)) return alt;
  return IMG[b.category]||"mixed.jpg";
}
function boxCard(b){
  const fomo=b.qty_left<=3;
  return `<article class="boxc" data-id="${b.id}">
    <div class="top" style="background-image:url(/static/img/${imgFor(b)})">
      <span class="bdg b-disc">${b.emoji} −${b.discount}%</span>
      <span class="bdg b-left${fomo?" fomo":""}">${fomo?"🔥 ":""}осталось ${b.qty_left}</span>
      <button class="b-fav${favs().includes(b.partner_id)?" on":""}" title="Любимая кофейня"
        data-act="toggleFav" data-a1="${b.partner_id}" data-stop="1">♥</button></div>
    <div class="body">
      <div class="trow"><h3>${esc(b.title||b.partner_name)}</h3>
        <button class="rt" data-pid="${b.partner_id}" data-name="${esc(b.partner_name)}" data-act="showReviews" data-stop="1">⭐ ${b.rating}</button></div>
      <div class="ven">${esc(b.partner_name)}</div>
      <div class="meta2">📍 ${esc(b.district)} · ⏱ ${win(b.pickup_from,b.pickup_to)}</div>
      <div class="price"><b>${money(b.price)}</b><s>${money(b.value_est)}</s></div>
    </div></article>`;
}
/* карта */
$("#vList").onclick=()=>{mapMode=false;$("#vList").classList.add("on");$("#vMap").classList.remove("on");$("#map").classList.add("hidden");$("#boxes").classList.remove("hidden");};
$("#vMap").onclick=()=>{mapMode=true;$("#vMap").classList.add("on");$("#vList").classList.remove("on");$("#boxes").classList.add("hidden");$("#map").classList.remove("hidden");renderMap();};
/* подложку карты легко сменить на 2GIS MapGL, когда будет API-ключ (dev.2gis.com) */
async function renderMap(){
  let ps=[];try{ps=await get("/partners");}catch(e){return;}
  if(!mapObj){
    mapObj=L.map("map").setView([51.128,71.43],12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(mapObj);
    mapObj._icon=L.icon({iconUrl:"/static/img/logo.png",iconSize:[34,34],iconAnchor:[17,34],popupAnchor:[0,-30]});
  }
  setTimeout(()=>mapObj.invalidateSize(),100);
  if(mapObj._markers)mapObj._markers.forEach(m=>m.remove());
  mapObj._markers=ps.map(p=>{
    const pb=ALL_BOXES.filter(b=>b.partner_id===p.id);
    const n=pb.reduce((s,b)=>s+b.qty_left,0);
    const minP=pb.length?Math.min(...pb.map(b=>b.price)):null;
    const html=`<div style="font-family:inherit;min-width:190px">
      <b style="color:var(--brown);font-size:.95rem">${esc(p.name)}</b>
      <div style="font-size:.76rem;color:#7E6A5A;margin:.15rem 0 .4rem">${esc(p.address)} · ⭐ ${p.rating}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem">
        <span style="background:#FFF5D6;color:#7E5233;padding:2px 8px;border-radius:7px;font-size:.72rem;font-weight:700">${n} ${plural(n,["бокс","бокса","боксов"])}</span>
        ${minP?`<b style="color:var(--brown)">от ${money(minP)}</b>`:""}
      </div>
      ${n?`<button class="map-shop" data-act="mapShop" data-name="${esc(p.name)}" style="width:100%;background:oklch(22% .03 45);border:0;padding:8px;border-radius:999px;font-weight:700;color:oklch(97% .018 82);cursor:pointer;font-family:inherit">Смотреть боксы</button>`:'<span style="font-size:.74rem;color:#7E6A5A">Сегодня боксов нет</span>'}
      <a href="https://2gis.kz/astana/directions/points/%7C${p.lng}%2C${p.lat}" target="_blank" rel="noopener"
        style="display:block;text-align:center;margin-top:6px;font-size:.76rem;font-weight:700;color:#653624">🗺 Маршрут в 2ГИС</a>
    </div>`;
    return L.marker([p.lat,p.lng],{icon:mapObj._icon,title:p.name}).addTo(mapObj).bindPopup(html);
  });
}
function shopFromMap(name){
  curQuery=name.toLowerCase();
  ["q","qm"].forEach(id=>{const e=$("#"+id);if(e)e.value=name;});
  $("#vList").click();                                     // назад в список
  renderBoxes();
  setTimeout(()=>$("#boxes").scrollIntoView({behavior:"smooth"}),150);
}

