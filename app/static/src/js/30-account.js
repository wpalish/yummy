/* ============ АККАУНТ / ОНБОРДИНГ ============ */
const ROLE_RU={buyer:"Покупатель",partner:"Заведение",guest:"Гость"};
/* Токены НЕ живут в localStorage (XSS-кража сессии): access — только в памяти,
   refresh — в httpOnly-cookie (JS его не видит). В сторадже — только метаданные
   профиля. После перезагрузки сессия молча восстанавливается по cookie. */
const SESSION={token:"",refresh:""};
function account(){
  try{
    const a=JSON.parse(localStorage.getItem("ym_account")||"null");
    if(a&&a.server){a.token=SESSION.token;a.refresh=SESSION.refresh;}
    return a;
  }catch(e){return null;}
}
function setAccount(a){
  const meta={...a};
  if(meta.server){ SESSION.token=meta.token||SESSION.token; SESSION.refresh=meta.refresh||"";
    delete meta.token; delete meta.refresh; }
  localStorage.setItem("ym_account",JSON.stringify(meta));renderAccount();
}
async function restoreSession(){
  const a=account();
  if(!a||!a.server||SESSION.token)return false;
  try{
    const base=(typeof API_BASE!=="undefined"?API_BASE:"");
    const r=await fetch(base+"/auth/refresh",{method:"POST",credentials:"include",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:""})});
    if(!r.ok)return false;
    const j=await r.json();
    SESSION.token=j.access_token;                 // refresh остался в cookie
    return true;
  }catch(e){return false;}
}
function renderAccount(){
  const a=account(), btn=$("#acctBtn");
  applyStaffVisibility();   // вкладки Партнёр/Админ — только своей роли
  if(!a){btn.innerHTML='<span class="av">?</span><span class="nm">Войти</span>';btn.onclick=showOnboarding;return;}
  const ini=((a.name||"?").trim()[0]||"?").toUpperCase();
  btn.innerHTML=`<span class="av">${esc(ini)}</span><span class="nm">${esc(a.name||ROLE_RU[a.role])}</span>`;
  btn.onclick=acctMenu;
}
function acctMenu(){
  const a=account()||{};
  showModal(`<div class="mc">
    <h3>${esc(a.name||"Профиль")}</h3>
    <p style="color:var(--txt2);font-size:.85rem;margin:.1rem 0 .9rem">Вы вошли как <b style="color:var(--brown)">${ROLE_RU[a.role]||"гость"}</b>${a.phone?" · "+esc(a.phone):""}</p>
    <button class="btn" data-act="closeGotoOrders">🛒 Мои заказы</button>
    ${a.token?`<button class="btn sec" style="margin-top:.5rem" data-act="changePwForm">🔑 Сменить пароль</button>
    <button class="btn sec" style="margin-top:.5rem" data-act="logoutAll">🚪 Выйти со всех устройств</button>
    <button class="btn sec" style="margin-top:.5rem" data-act="exportMe">⬇ Скачать мои данные</button>
    <button class="btn sec" style="margin-top:.5rem;color:var(--red)" data-act="deleteMeConfirm">🗑 Удалить аккаунт</button>`:""}
    <button class="btn sec" style="margin-top:.5rem" data-act="closeShowOnb">Сменить роль</button>
    <button class="btn sec" style="margin-top:.5rem" data-act="logout">Выйти</button>
  </div>`);
}
/* Privacy + сессии (Sentinel-паттерны, реализованные честно) */
window.logoutAll=async()=>{
  try{await post("/auth/logout-all");}catch(e){}
  toast("Вышли со всех устройств"); logout();
};
window.exportMe=async()=>{
  try{
    const d=await get("/me/export");
    const a=document.createElement("a");
    a.href="data:application/json;charset=utf-8,"+encodeURIComponent(JSON.stringify(d,null,2));
    a.download="yummy-data.json"; document.body.appendChild(a); a.click(); a.remove();
    toast("Данные скачаны ⬇");
  }catch(e){toast(e.message,true);}
};
window.deleteMeConfirm=()=>{
  showModal(`<div class="mc">
    <h3>Удалить аккаунт?</h3>
    <p style="font-size:.86rem;color:var(--txt2);margin:.3rem 0 .9rem">Данные заказов обезличатся, вход станет невозможен. Действие необратимо.</p>
    <button class="btn" style="background:var(--red);color:#fff" id="delBtn">Да, удалить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#delBtn").onclick=async()=>{
    try{await api("DELETE","/me"); toast("Аккаунт удалён"); logout();}
    catch(e){toast(e.message,true);}
  };
};
window.changePwForm=()=>{
  showModal(`<div class="mc">
    <h3>Сменить пароль</h3>
    <label>Текущий пароль <input id="pwOld" type="password" autocomplete="current-password" /></label>
    <label>Новый пароль <input id="pwNew" type="password" placeholder="Мин. 8 символов, буквы и цифры" autocomplete="new-password" /><span class="ferr" id="pw_err"></span></label>
    <button class="btn" id="pwBtn" style="margin-top:.7rem">Сохранить</button>
    <button class="btn sec" data-act="closeModal" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#pwBtn").onclick=async()=>{
    const old=$("#pwOld").value, nw=$("#pwNew").value;
    const pe=_pwErr(nw); if(pe){$("#pw_err").textContent=pe;return;}
    try{ const r=await post("/auth/change-password",{old_password:old,new_password:nw});
      if(r&&r.access_token){const a=account();a.token=r.access_token;a.refresh=r.refresh_token||a.refresh;setAccount(a);}  // старые сессии отозваны, эта — обновлена
      closeModal(); toast("Пароль изменён ✓ Остальные устройства разлогинены"); }
    catch(e){ $("#pw_err").textContent=e.message; }
  };
};
function logout(){localStorage.removeItem("ym_account");closeModal();renderAccount();switchView("store");showOnboarding();}
function hideOnboarding(){$("#onboard").className="hidden";$("#onboard").innerHTML="";}
function showOnboarding(){
  const o=$("#onboard");o.className="onb";
  o.innerHTML=`<div class="onb-card">
    <div class="onb-logo"><img src="/static/img/logo.png" alt=""><b>Yummy</b></div>
    <h2>Добро пожаловать 👋</h2>
    <p class="lead">Спасайте свежую еду из кофеен и пекарен Астаны со скидкой до 70%. Кто вы?</p>
    <button class="role-card" data-act="onbBuyer"><span class="ic">🛍️</span><div><div class="t">Я покупатель</div><div class="d">Бронировать и забирать сюрприз-боксы</div></div></button>
    <button class="role-card" data-act="onbPartner"><span class="ic">☕</span><div><div class="t">Я заведение</div><div class="d">Кофейня/пекарня — продавать вечерние излишки</div></div></button>
    <button class="guest" data-act="loginForm">Уже есть аккаунт? Войти</button>
    <button class="guest" data-act="onbGuest">Пропустить, просто осмотреться →</button>
  </div>`;
}
/* Вход по email+паролю → POST /auth/login (роль приходит с сервера) */
function loginForm(){
  const o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <button class="onb-back" data-act="showOnboarding">← Назад</button>
    <h2>Вход</h2>
    <p class="lead">Войдите в аккаунт покупателя или заведения.</p>
    <label>Email <input id="lgEmail" type="email" placeholder="you@email.com" autocomplete="email" /><span class="ferr" id="le_email"></span></label>
    <label>Пароль <span class="pw"><input id="lgPass" type="password" autocomplete="current-password" />
      <button type="button" class="pw-t" id="lgToggle" aria-label="Показать пароль">👁</button></span><span class="ferr" id="le_pass"></span></label>
    <button class="btn" id="lgBtn" style="margin-top:.5rem">Войти</button>
    <button class="guest" data-act="forgotPw" style="margin-top:.4rem">Забыли пароль?</button>
  </div>`;
  $("#lgEmail").focus();
  $("#lgToggle").onclick=()=>{const p=$("#lgPass");p.type=p.type==="password"?"text":"password";};
  $("#lgBtn").onclick=async()=>{
    const email=$("#lgEmail").value.trim(), pass=$("#lgPass").value;
    $("#le_email").textContent=""; $("#le_pass").textContent="";
    if(!_emailOk(email)){$("#le_email").textContent="Некорректный email";return;}
    if(!pass){$("#le_pass").textContent="Введите пароль";return;}
    const btn=$("#lgBtn"); btn.disabled=true; btn.textContent="Входим…";
    try{
      const res=await post("/auth/login",{email,password:pass});
      const u=res.user, roleMap={customer:"buyer",partner:"partner",admin:"admin"};
      const acc={role:roleMap[u.role]||"buyer",name:u.brand_name||email.split("@")[0],email,
        token:res.access_token,refresh:res.refresh_token||"",server:true,createdAt:Date.now(),
        partner_role:u.partner_role||null,partner_id:u.partner_id||null};
      setAccount(acc);
      hideOnboarding();
      toast(`С возвращением${acc.name?", "+acc.name:""}!`);
      switchView(u.role==="partner"?"partner":u.role==="admin"?"admin":"store");
    }catch(e){
      if(/404|Failed|fetch|NetworkError|Load failed/i.test(e.message)){
        // статичная демо-версия: настоящего входа нет (нет сервера/пароля) —
        // мягко пускаем в демо-профиль вместо тупика
        setAccount({role:"buyer",name:email.split("@")[0],email,server:false,createdAt:Date.now()});
        hideOnboarding(); toast("Демо-вход (без сервера). Настоящий вход — после деплоя бэкенда");
        switchView("store"); return;
      }
      if(e.message==="totp_required"&&!$("#lgTotp")){
        // 2FA включена: дорисовываем поле кода и повторяем вход с ним
        btn.insertAdjacentHTML("beforebegin",
          `<label>Код из приложения-аутентификатора
             <input id="lgTotp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="123456" /></label>`);
        const orig=$("#lgBtn").onclick;
        $("#lgBtn").onclick=async()=>{
          const code=$("#lgTotp").value.trim();
          if(code.length!==6){toast("Введите 6-значный код",true);return;}
          const b2=$("#lgBtn"); b2.disabled=true; b2.textContent="Проверяем…";
          try{
            const res=await post("/auth/login",{email,password:pass,totp:code});
            const u=res.user, roleMap={customer:"buyer",partner:"partner",admin:"admin"};
            setAccount({role:roleMap[u.role]||"buyer",name:u.brand_name||email.split("@")[0],email,
              token:res.access_token,refresh:res.refresh_token||"",server:true,createdAt:Date.now(),
              partner_role:u.partner_role||null,partner_id:u.partner_id||null});
            hideOnboarding(); toast("С возвращением!");
            switchView(u.role==="partner"?"partner":u.role==="admin"?"admin":"store");
          }catch(err){toast(err.message,true);b2.disabled=false;b2.textContent="Войти";}
        };
        $("#lgTotp").focus(); btn.disabled=false; btn.textContent="Войти"; return;
      }
      $("#le_pass").textContent=e.message;  // реальный бэкенд: «Неверный email или пароль» и т.п.
      btn.disabled=false; btn.textContent="Войти";
    }
  };
}
/* Сброс пароля: запрос ссылки и форма по ?reset=TOKEN из письма */
function forgotPwForm(){
  const o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <button class="onb-back" data-act="loginForm">← Назад</button>
    <h2>Сброс пароля</h2>
    <p class="lead">Пришлём ссылку для сброса на почту аккаунта.</p>
    <label>Email <input id="fpEmail" type="email" autocomplete="email" /></label>
    <button class="btn" id="fpBtn" style="margin-top:.5rem">Отправить ссылку</button>
    <div id="fpHint" style="margin-top:.6rem;font-size:.84rem;color:var(--txt2)"></div>
  </div>`;
  $("#fpEmail").focus();
  $("#fpBtn").onclick=async()=>{
    const email=$("#fpEmail").value.trim();
    if(!_emailOk(email)){toast("Некорректный email",true);return;}
    const b=$("#fpBtn"); b.disabled=true; b.textContent="Отправляем…";
    try{ const r=await post("/auth/request-reset",{email}); $("#fpHint").textContent=r.hint; }
    catch(e){ toast(e.message,true); }
    b.disabled=false; b.textContent="Отправить ссылку";
  };
}
function resetPwForm(token){
  $("#onboard").className="onb";
  const o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <h2>Новый пароль</h2>
    <p class="lead">Придумайте новый пароль — минимум 8 символов, буквы и цифры.</p>
    <label>Новый пароль <input id="rpPass" type="password" autocomplete="new-password" /><span class="ferr" id="rp_err"></span></label>
    <button class="btn" id="rpBtn" style="margin-top:.5rem">Сменить пароль</button>
  </div>`;
  $("#rpBtn").onclick=async()=>{
    const pw=$("#rpPass").value, err=_pwErr(pw);
    if(err){$("#rp_err").textContent=err;return;}
    const b=$("#rpBtn"); b.disabled=true; b.textContent="Меняем…";
    try{
      await post("/auth/reset-password",{token,password:pw});
      toast("Пароль изменён — войдите с новым паролем ✓");
      history.replaceState(null,"",location.pathname);   // токен из URL убираем
      loginForm();
    }catch(e){ $("#rp_err").textContent=e.message; b.disabled=false; b.textContent="Сменить пароль"; }
  };
}
const _emailOk=v=>/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
const _pwErr=v=>v.length<8?"Минимум 8 символов":(!/[a-zа-яA-ZА-Я]/.test(v)||!/[0-9]/.test(v))?"Нужны буквы и цифры":"";
/* Регистрация: пробуем реальный бэкенд POST /auth/register; на статике Pages —
   локальный фолбэк (пароль в браузере НЕ храним). */
async function tryRegister(payload){
  try{ return {mode:"server",res:await post("/auth/register",payload)}; }
  catch(e){
    if(/зарегистрирован|занят|409/i.test(e.message)) throw e;  // реальный дубль email
    return {mode:"local"};                                      // бэкенда нет
  }
}
function onbBuyer(){ regForm("buyer"); }
/* Заведения подключаются ТОЛЬКО по приглашению админа (одноразовая ссылка):
   саморегистрация партнёра закрыта на бэкенде (403), иначе доступ к партнёрке
   получил бы любой. Здесь — честная заявка вместо формы. */
function onbPartner(){
  const o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <button class="onb-back" data-act="showOnboarding">← Назад к выбору роли</button>
    <h2>Заведениям</h2>
    <p class="lead">Кофейни и пекарни подключаются по приглашению: мы проверяем заведение и высылаем ссылку для входа в кабинет.</p>
    <p style="font-size:.88rem;color:var(--txt2);margin:.2rem 0 1rem">Напишите нам название, адрес и контакт — ответим и пришлём доступ.</p>
    <a class="btn" style="display:block;text-decoration:none" href="mailto:alisher.nursain@gmail.com?subject=Хочу%20стать%20партнёром%20Yummy&body=Заведение:%0AАдрес:%0AКонтакт:">✉️ Оставить заявку</a>
    <button class="btn sec" style="margin-top:.5rem" data-act="guestStore">Сначала посмотрю боксы</button>
  </div>`;
}
function regForm(role){
  const partner=role==="partner", o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <button class="onb-back" data-act="showOnboarding">← Назад к выбору роли</button>
    <h2>${partner?"Регистрация заведения":"Создать аккаунт"}</h2>
    <p class="lead">${partner?"Кабинет владельца кофейни или пекарни.":"Личный кабинет покупателя."}</p>
    ${partner
      ?`<label>Название заведения <input id="rgName" placeholder="Напр.: Coffee Point" autocomplete="organization" /><span class="ferr" id="e_name"></span></label>`
      :`<label>Имя <input id="rgName" placeholder="Как к вам обращаться" autocomplete="name" /><span class="ferr" id="e_name"></span></label>`}
    <label>Email <input id="rgEmail" type="email" placeholder="you@email.com" autocomplete="email" /><span class="ferr" id="e_email"></span></label>
    <label>Пароль <span class="pw"><input id="rgPass" type="password" placeholder="Минимум 8 символов, буквы и цифры" autocomplete="new-password" />
      <button type="button" class="pw-t" id="pwToggle" aria-label="Показать пароль">👁</button></span><span class="ferr" id="e_pass"></span></label>
    <label class="consent"><input type="checkbox" id="rgConsent" />
      <span>Принимаю <a data-act="showLegal" data-a1="offer">оферту</a> и даю согласие на обработку персональных данных согласно <a data-act="showLegal" data-a1="privacy">политике</a>.${partner?` Принимаю <a data-act="showLegal" data-a1="agreement">договор</a> и <a data-act="showLegal" data-a1="quality">стандарты пищевой безопасности</a>.`:""}</span></label>
    <span class="ferr" id="e_consent"></span>
    <button class="btn" id="rgBtn" style="margin-top:.4rem">Зарегистрироваться</button>
  </div>`;
  $("#rgName").focus();
  $("#pwToggle").onclick=()=>{const p=$("#rgPass");p.type=p.type==="password"?"text":"password";};
  $("#rgBtn").onclick=async()=>{
    const setE=(id,m)=>$("#"+id).textContent=m||"";
    ["e_name","e_email","e_pass"].forEach(id=>setE(id,""));
    const name=$("#rgName").value.trim(), email=$("#rgEmail").value.trim(), pass=$("#rgPass").value;
    let bad=false;
    if(name.length<2){setE("e_name",partner?"Укажите название заведения":"Введите имя");bad=true;}
    if(!_emailOk(email)){setE("e_email","Некорректный email");bad=true;}
    const pe=_pwErr(pass); if(pe){setE("e_pass",pe);bad=true;}
    if(!$("#rgConsent").checked){setE("e_consent","Необходимо согласие с офертой и обработкой данных");bad=true;}
    if(bad)return;
    const btn=$("#rgBtn"); btn.disabled=true; btn.textContent="Создаём аккаунт…";
    try{
      const payload=partner?{email,password:pass,role:"partner",brand_name:name}:{email,password:pass,role:"customer"};
      let out;
      try{ out=await tryRegister(payload); }
      catch(e){ setE("e_email",e.message); btn.disabled=false; btn.textContent="Зарегистрироваться"; return; }
      // роль приходит с сервера: публичная регистрация = только покупатель
      const srvRole=(out.res&&out.res.user&&out.res.user.role)||"customer";
      const acc={role:srvRole==="admin"?"admin":"buyer",name,email,createdAt:Date.now(),server:out.mode==="server"};
      if(out.mode==="server"&&out.res&&out.res.access_token){acc.token=out.res.access_token;acc.refresh=out.res.refresh_token||"";}
      setAccount(acc);
      hideOnboarding();
      toast(out.mode==="server"?"Аккаунт создан ✓":"Профиль создан (демо). Добро пожаловать!");
      switchView("store");
    }catch(e){ toast(e.message,true); btn.disabled=false; btn.textContent="Зарегистрироваться"; }
  };
}
function onbGuest(){setAccount({role:"guest",name:"Гость",createdAt:Date.now()});hideOnboarding();}

