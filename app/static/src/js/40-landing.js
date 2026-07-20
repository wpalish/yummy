/* ============ ЛЕНДИНГ: инлайн-регистрация + reveal-анимации ============ */
window.openLogin=()=>{$("#onboard").className="onb";loginForm();};
window.__landRole="buyer";
window.landRole=r=>{
  window.__landRole=r;
  $("#lr-buyer").classList.toggle("on",r==="buyer");
  $("#lr-partner").classList.toggle("on",r==="partner");
  $("#lrNameL").textContent=r==="partner"?"Название заведения":"Имя";
  $("#lrName").placeholder=r==="partner"?"Напр.: Coffee Point":"Как к вам обращаться";
};
$("#lrT").onclick=()=>{const p=$("#lrPass");p.type=p.type==="password"?"text":"password";};
$("#lrBtn").onclick=async()=>{
  const partner=false;   // лендинг-форма регистрирует только покупателя (заведения — по инвайту)
  const setE=(id,m)=>$("#"+id).textContent=m||"";
  ["lr_name","lr_email","lr_pass"].forEach(id=>setE(id,""));
  const name=$("#lrName").value.trim(), email=$("#lrEmail").value.trim(), pass=$("#lrPass").value;
  let bad=false;
  if(name.length<2){setE("lr_name",partner?"Укажите название заведения":"Введите имя");bad=true;}
  if(!_emailOk(email)){setE("lr_email","Некорректный email");bad=true;}
  const pe=_pwErr(pass); if(pe){setE("lr_pass",pe);bad=true;}
  if(!$("#lrConsent").checked){setE("lr_consent","Необходимо согласие с офертой и обработкой данных");bad=true;}
  if(bad)return;
  const btn=$("#lrBtn"); btn.disabled=true; btn.textContent="Создаём аккаунт…";
  try{
    const payload=partner?{email,password:pass,role:"partner",brand_name:name}:{email,password:pass,role:"customer"};
    let out;
    try{ out=await tryRegister(payload); }
    catch(e){ setE("lr_email",e.message); btn.disabled=false; btn.textContent="Зарегистрироваться"; return; }
    const srvRole=(out.res&&out.res.user&&out.res.user.role)||"customer";
    const acc={role:srvRole==="admin"?"admin":"buyer",name,email,createdAt:Date.now(),server:out.mode==="server"};
    if(out.mode==="server"&&out.res&&out.res.access_token){acc.token=out.res.access_token;acc.refresh=out.res.refresh_token||"";}
    setAccount(acc);
    toast(out.mode==="server"?"Аккаунт создан ✓":"Профиль создан (демо). Добро пожаловать!");
    switchView("store");
  }catch(e){ toast(e.message,true); }
  btn.disabled=false; btn.textContent="Зарегистрироваться";
};
/* плавное появление секций при скролле: IO + fallback (элементы стартуют в
   display:none-контейнере — не все движки шлют entry после показа) */
function revealCheck(){
  const vh=innerHeight||document.documentElement.clientHeight||800;
  document.querySelectorAll(".reveal:not(.in)").forEach(el=>{
    const r=el.getBoundingClientRect();
    if(r.top<vh*.9&&r.bottom>0)el.classList.add("in");
  });
}
try{
  const _io=new IntersectionObserver(es=>es.forEach(e=>{
    if(e.isIntersecting){e.target.classList.add("in");_io.unobserve(e.target);}
  }),{threshold:.12});
  document.querySelectorAll(".reveal").forEach(el=>_io.observe(el));
}catch(e){}
addEventListener("scroll",revealCheck,{passive:true});
addEventListener("resize",revealCheck,{passive:true});
// страховка для движков, где scroll-события не доходят: дешёвый тик на лендинге
setInterval(()=>{ if(window.__view==="landing")revealCheck(); },350);

/* ---- поиск ---- */
let _qT;
["q","qm"].forEach(id=>{const el=$("#"+id);if(el)el.addEventListener("input",()=>{
  curQuery=el.value.trim().toLowerCase();
  const other=$(id==="q"?"#qm":"#q");if(other&&other.value!==el.value)other.value=el.value;   // синк desktop/mobile
  clearTimeout(_qT);_qT=setTimeout(renderBoxes,180);                                          // дебаунс
});});

