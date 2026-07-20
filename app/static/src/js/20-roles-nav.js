/* ---- роли + bottom-nav + демо-доступ персонала ---- */
const roleBtns=[...document.querySelectorAll(".roles button")];
const navBtns=[...document.querySelectorAll(".bnav button")];
/* Партнёрка/админка — только по роли аккаунта. Демо-PIN убран: партнёром
   становятся ТОЛЬКО по инвайту админа (/auth/accept-invite), покупатель эти
   разделы не видит вовсе (см. applyStaffVisibility). Настоящая защита — на
   бэкенде (require_role + JWT); здесь скрываем UI, чтобы не путать клиентов. */
const STAFF_VIEWS={partner:["partner","admin"],admin:["admin"]};
function staffRole(){const a=account();return a&&a.role?a.role:"guest";}
function canView(v){return (STAFF_VIEWS[v]||[]).includes(staffRole());}
function applyStaffVisibility(){
  ["partner","admin"].forEach(v=>{
    const ok=canView(v);
    roleBtns.forEach(b=>{if(b.dataset.role===v)b.classList.toggle("hidden",!ok);});
    navBtns.forEach(b=>{if(b.dataset.nav===v)b.classList.toggle("hidden",!ok);});
  });
}
function requireStaff(cb){
  if(canView(window.__wantView||"partner")){cb();return;}
  showModal(`<div class="mc">
    <h3>Раздел для заведений</h3>
    <p style="font-size:.85rem;color:var(--txt2);margin:.3rem 0 .9rem">Партнёрская панель доступна заведениям-партнёрам Yummy. Подключение — по приглашению: напишите нам, и мы вышлем ссылку для входа.</p>
    <a class="btn" style="display:block;text-decoration:none" href="mailto:alisher.nursain@gmail.com?subject=Хочу%20стать%20партнёром%20Yummy">✉️ Стать партнёром</a>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Закрыть</button>
  </div>`);
}
function switchView(v){
  const go=()=>{
    window.__view=v;
    document.body.classList.toggle("on-landing",v==="landing");
    roleBtns.forEach(x=>x.classList.toggle("on",x.dataset.role===v));
    navBtns.forEach(x=>x.classList.toggle("on",x.dataset.nav===v));
    ["landing","store","venues","partner","admin"].forEach(s=>$("#view-"+s).classList.toggle("hidden",s!==v));
    if(v==="store")loadStore(); if(v==="venues")loadVenues(); if(v==="partner")loadPartner(); if(v==="admin")loadAdmin();
    window.scrollTo({top:0});
    if(v==="landing")setTimeout(revealCheck,60);
  };
  window.__wantView=v;
  (v==="partner"||v==="admin")?requireStaff(go):go();
}
roleBtns.forEach(b=>b.onclick=()=>switchView(b.dataset.role));
navBtns.forEach(b=>b.onclick=()=>{
  const n=b.dataset.nav;
  if(n==="orders"){switchView("store");setTimeout(()=>$("#myorders").scrollIntoView({behavior:"smooth"}),250);
    navBtns.forEach(x=>x.classList.toggle("on",x===b));return;}
  switchView(n);
});
function gotoOrders(){switchView("store");setTimeout(()=>$("#myorders").scrollIntoView({behavior:"smooth"}),250);}
function scrollToBoxes(){$("#boxes").scrollIntoView({behavior:"smooth",block:"start"});}

