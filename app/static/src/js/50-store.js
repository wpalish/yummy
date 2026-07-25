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
  // координаты живут на партнёре (у Box их нет) — кэшируем для расчёта расстояния
  try{ (await get("/partners")).forEach(p=>{PARTNER_GEO[p.id]={lat:p.lat,lng:p.lng};}); }catch(e){}
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
  const bs=sortBoxes(filtered());
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
/* ---- сортировка и геолокация ---- */
let curSort="default", myPos=null;   // myPos — {lat,lng} после явного согласия пользователя
const PARTNER_GEO={};                // partner_id → {lat,lng}; у Box координат нет
const R_EARTH=6371;                  // км, для формулы гаверсинуса
function distKm(a,b){
  const rad=d=>d*Math.PI/180;
  const dLat=rad(b.lat-a.lat), dLng=rad(b.lng-a.lng);
  const h=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLng/2)**2;
  return 2*R_EARTH*Math.asin(Math.sqrt(h));
}
function boxDist(b){ // расстояние до заведения бокса, если координаты и позиция известны
  const g=PARTNER_GEO[b.partner_id];
  if(!myPos||!g)return null;
  return distKm(myPos,g);
}
function distLabel(b){ const d=boxDist(b); return d==null?"":`${d<1?Math.round(d*1000)+" м":d.toFixed(1)+" км"}`; }
function sortBoxes(bs){
  const a=[...bs];                                   // не мутируем исходный массив
  if(curSort==="cheap")a.sort((x,y)=>x.price-y.price);
  else if(curSort==="disc")a.sort((x,y)=>y.discount-x.discount);
  else if(curSort==="soon")a.sort((x,y)=>Date.parse(x.pickup_from)-Date.parse(y.pickup_from));
  else if(curSort==="near"&&myPos)a.sort((x,y)=>(boxDist(x)??1e9)-(boxDist(y)??1e9));
  return a;
}
$("#sortBy").onchange=e=>{
  curSort=e.target.value;
  if(curSort==="near"&&!myPos){ askGeo(); }
  renderBoxes(); if(mapMode)renderMapList();
};
/* Геолокация только по явному действию пользователя (клик), с честным фолбэком. */
function askGeo(){
  if(!navigator.geolocation){toast("Геолокация не поддерживается браузером",true);return;}
  toast("Определяем ваше местоположение…");
  navigator.geolocation.getCurrentPosition(
    p=>{ myPos={lat:p.coords.latitude,lng:p.coords.longitude};
         toast("Местоположение определено 📍"); renderBoxes(); if(mapMode){renderMapList();renderMap();} },
    ()=>toast("Не удалось получить местоположение — разрешите доступ в браузере",true),
    {enableHighAccuracy:false,timeout:8000,maximumAge:300000});
}
$("#geoBtn").onclick=askGeo;

/* карта */
$("#vList").onclick=()=>{mapMode=false;$("#vList").classList.add("on");$("#vMap").classList.remove("on");
  $("#storeSplit").classList.add("hidden");$("#boxes").classList.remove("hidden");};
$("#vMap").onclick=()=>{mapMode=true;$("#vMap").classList.add("on");$("#vList").classList.remove("on");
  $("#boxes").classList.add("hidden");$("#storeSplit").classList.remove("hidden");renderMapList();renderMap();};
/* Список боксов рядом с картой: клик по строке — открыть попап нужной точки. */
function renderMapList(){
  const bs=sortBoxes(filtered()), el=$("#mapList");
  if(!bs.length){el.innerHTML='<p class="empty">Ничего не нашлось.</p>';return;}
  el.innerHTML=bs.map(b=>{
    const d=distLabel(b);
    return `<article class="mrow" data-id="${b.id}" data-pid="${b.partner_id}">
      <img src="/static/img/${imgFor(b)}" alt="" loading="lazy" width="56" height="56">
      <div class="g"><b>${esc(b.title||b.partner_name)}</b>
        <span class="v">${esc(b.partner_name)}</span>
        <div class="p">📍 ${esc(b.district)}${d?" · "+d:""} · ⏱ ${win(b.pickup_from,b.pickup_to)}</div></div>
      <span class="pr">${money(b.price)}</span></article>`;
  }).join("");
  el.querySelectorAll(".mrow").forEach(r=>r.onclick=()=>{
    el.querySelectorAll(".mrow").forEach(x=>x.classList.remove("on"));
    r.classList.add("on");
    focusPartnerOnMap(r.dataset.pid);
  });
}
function focusPartnerOnMap(pid){
  if(!mapObj||!mapObj._byPartner)return;
  const mk=mapObj._byPartner[pid]; if(!mk)return;
  mapObj.setView(mk.getLatLng(),15,{animate:true}); mk.openPopup();
}
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
  mapObj._byPartner={};
  mapObj._markers=ps.map(p=>{
    const pb=ALL_BOXES.filter(b=>b.partner_id===p.id);
    const n=pb.reduce((s,b)=>s+b.qty_left,0);
    const top=pb.length?pb.reduce((a,b)=>a.price<=b.price?a:b):null;   // самый дешёвый — его и показываем
    const d=top?distLabel(top):"";
    // Карточка-попап как в референсе: фото, название, оффер, рейтинг, расстояние, цена, CTA
    const html=`<div class="mpop">
      ${top?`<img src="/static/img/${imgFor(top)}" alt="" loading="lazy">`:""}
      <div class="mpop-b">
        <b>${esc(p.name)}</b>
        ${top?`<div class="s">${esc(top.title||top.category_ru)}</div>`:""}
        <div class="m">⭐ ${p.rating}${d?" · "+d:""} · ${esc(p.address)}</div>
        ${top?`<div class="pr"><b>${money(top.price)}</b><s>${money(top.value_est)}</s>
          <span class="dsc">−${top.discount}%</span></div>`:""}
        ${n?`<button class="mpop-cta" data-act="openBox" data-a1="${esc(top.id)}">Забронировать</button>
             <div class="n">${n} ${plural(n,["бокс","бокса","боксов"])} в наличии</div>`
           :'<div class="n">Сегодня боксов нет</div>'}
        <a href="https://2gis.kz/astana/directions/points/%7C${p.lng}%2C${p.lat}" target="_blank" rel="noopener">🗺 Маршрут в 2ГИС</a>
      </div></div>`;
    const mk=L.marker([p.lat,p.lng],{icon:mapObj._icon,title:p.name}).addTo(mapObj)
      .bindPopup(html,{minWidth:264,maxWidth:280,className:"mpop-wrap"});
    mapObj._byPartner[p.id]=mk;
    return mk;
  });
  // Своя точка — отдельным маркером, только если пользователь сам её разрешил
  if(myPos){
    if(mapObj._me)mapObj._me.remove();
    mapObj._me=L.circleMarker([myPos.lat,myPos.lng],
      {radius:8,fillColor:"#2C7BE5",color:"#fff",weight:3,fillOpacity:1}).addTo(mapObj).bindPopup("Вы здесь");
    mapObj.setView([myPos.lat,myPos.lng],13,{animate:true});
  }
}
function shopFromMap(name){
  curQuery=name.toLowerCase();
  ["q","qm"].forEach(id=>{const e=$("#"+id);if(e)e.value=name;});
  $("#vList").click();                                     // назад в список
  renderBoxes();
  setTimeout(()=>$("#boxes").scrollIntoView({behavior:"smooth"}),150);
}

