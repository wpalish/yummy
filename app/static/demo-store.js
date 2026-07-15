/* ===== CLIENT-SIDE STORE (GitHub Pages, без бэкенда) — имитирует REST API ===== */
const CAT_RU={sweet:"Сладкий бокс",bakery:"Бокс выпечки",mixed:"Микс-бокс",snack:"Снек-бокс"};
const CAT_EM={sweet:"🍩",bakery:"🥐",mixed:"🧺",snack:"🥪"};
const PARTNERS=[
 {id:"p1",name:"Coffee Point",district:"Есильский р-н",address:"пр. Мангилик Ел, 55",rating:4.8,lat:51.090,lng:71.416},
 {id:"p2",name:"Bake House",district:"Сарыарка р-н",address:"ул. Бейбитшилик, 33",rating:4.7,lat:51.180,lng:71.408},
 {id:"p3",name:"Donut Lab",district:"Есильский р-н",address:"ТРЦ Mega Silk Way",rating:4.6,lat:51.089,lng:71.402},
 {id:"p4",name:"Сдоба",district:"Алматинский р-н",address:"ул. Кенесары, 40",rating:4.2,lat:51.165,lng:71.419},
 {id:"p5",name:"Sweet Corner",district:"Есильский р-н",address:"пр. Кабанбай батыра, 7",rating:4.9,lat:51.132,lng:71.437},
 {id:"p6",name:"Утром Кофе",district:"Алматинский р-н",address:"ул. Богенбай батыра, 23",rating:4.6,lat:51.166,lng:71.446}];
/* [id,pid,cat,title,price,value,qty,start_off_min,dur_h,desc] */
const SEED_BOXES=[
 ["b1","p1","sweet","Вечерний сладкий бокс",990,2600,5,-20,4,"Обычно внутри: 2 пончика, маффин и печенье. Состав меняется день ко дню."],
 ["b2","p1","snack","Снек-бокс",1190,2900,3,40,3,"Обычно внутри: сэндвич, круассан и выпечка дня."],
 ["b3","p2","bakery","Бокс выпечки",890,2400,6,-10,5,"Обычно внутри: 2 круассана, булочка с корицей, багет. Из утренней партии."],
 ["b4","p3","sweet","Donut Box",790,2200,8,90,4,"Обычно внутри: 6 пончиков ассорти (глазурь, шоколад, посыпка)."],
 ["b5","p4","mixed","Микс-бокс",1090,2800,4,0,3,"Обычно внутри: сэндвич + 2 позиции сладкой выпечки. Сюрприз дня."],
 ["b6","p5","sweet","Dessert Box",1290,3200,3,30,2,"Обычно внутри: 2 пирожных и десерт дня (чизкейк или тирамису)."],
 ["b7","p6","bakery","Утренняя выпечка",850,2300,5,-30,6,"Обычно внутри: 3–4 позиции свежей выпечки по вечерней цене."]];
const P_BY_ID=Object.fromEntries(PARTNERS.map(p=>[p.id,p]));
const SKEY="yummy_state_v2";
function round30(d){d=new Date(d);d.setMinutes(d.getMinutes()<30?0:30,0,0);return d;}
function freshState(){
  const now=Date.now();
  return {boxes:SEED_BOXES.map(([id,pid,cat,title,price,val,qty,off,dur,desc])=>{
      const from=round30(now+off*60000), to=new Date(from.getTime()+dur*3600000);
      return {id,partner_id:pid,category:cat,title,price,value_est:val,qty_total:qty,qty_left:qty,
        pickup_from:from.toISOString(),pickup_to:to.toISOString(),description:desc,
        created_at:new Date().toISOString(),status:"active"};}),
    orders:[],reviews:[],seq:100};
}
function saveState(s){localStorage.setItem(SKEY,JSON.stringify(s));}
function loadState(){try{const s=JSON.parse(localStorage.getItem(SKEY));
  if(s&&s.boxes){ // если все окна выдачи истекли — обновить демо-данные
    if(!s.reviews)s.reviews=[];               // миграция состояния без отзывов
    const anyLive=s.boxes.some(b=>Date.parse(b.pickup_to)>Date.now());
    if(anyLive)return s;
  }}catch(e){}
  const s=freshState();saveState(s);return s;}
let ST=loadState();
function persist(){saveState(ST);}
function effStatus(o){if(o.status==="paid"&&Date.now()>Date.parse(o.pickup_to))return "expired";return o.status;}
function boxView(b){const p=P_BY_ID[b.partner_id]||{};const disc=b.value_est>0?Math.round((1-b.price/b.value_est)*100):0;
  return {...b,partner_name:p.name||"—",district:p.district||"",address:p.address||"",rating:p.rating||0,
    discount:disc,category_ru:CAT_RU[b.category]||b.category,emoji:CAT_EM[b.category]||"🧺"};}
function orderView(o){const p=P_BY_ID[o.partner_id]||{};
  return {...o,status:effStatus(o),partner_name:p.name||"—",address:p.address||"",
    category_ru:CAT_RU[o.category]||o.category,emoji:CAT_EM[o.category]||"🧺"};}
function qrSvg(text){const qr=qrcode(0,"M");qr.addData(text);qr.make();return qr.createSvgTag({cellSize:6,margin:2});}
function newCode(){const a="23456789ABCDEFGHJKLMNPQRSTUVWXYZ";let s="";for(let i=0;i<10;i++)s+=a[Math.floor(Math.random()*a.length)];return `YM-${s.slice(0,5)}-${s.slice(5)}`;}
function statsCalc(){let gmv=0,issued=0,no_show=0,active=0,refunds=0;
  ST.orders.forEach(o=>{const s=effStatus(o);if(s==="paid"||s==="issued"||s==="expired")gmv+=o.price;
    if(s==="issued")issued++;else if(s==="expired")no_show++;else if(s==="paid")active++;else if(s==="refunded")refunds++;});
  const total=ST.orders.length,closed=issued+no_show;
  return {orders_total:total,issued,active,no_show,refunds,gmv,fill_rate:closed?Math.round(issued/closed*100):0};}
async function _demoGet(u){
  const [path,q]=u.split("?"); const qs=new URLSearchParams(q||""); let m;
  if(path==="/config")return {payment_mode:"demo",currency:"kzt"};
  if(path==="/districts")return [...new Set(PARTNERS.map(p=>p.district))].sort();
  if(path==="/boxes"){const d=qs.get("district");
    let bs=ST.boxes.filter(b=>b.status==="active"&&b.qty_left>0&&Date.parse(b.pickup_to)>Date.now()).map(boxView);
    if(d&&d!=="all")bs=bs.filter(b=>b.district===d); return bs;}
  if(m=path.match(/^\/boxes\/(.+)$/)){const b=ST.boxes.find(x=>x.id===m[1]);if(!b)throw new Error("Бокс не найден");return boxView(b);}
  if(m=path.match(/^\/orders\/(.+)$/)){const o=ST.orders.find(x=>x.code===decodeURIComponent(m[1]).toUpperCase());if(!o)throw new Error("Заказ не найден");
    const v=orderView(o);return {code:v.code,partner_name:v.partner_name,address:v.address,category:v.category,price:v.price,status:v.status,pickup_from:v.pickup_from,pickup_to:v.pickup_to,category_ru:v.category_ru,emoji:v.emoji};}
  if(path==="/partners")return PARTNERS;
  if(path==="/partner/me")return PARTNERS[0];
  if(path==="/partner/me/boxes")return ST.boxes.filter(b=>b.partner_id===PARTNERS[0].id).map(boxView);
  if(path==="/partner/me/orders")return ST.orders.filter(o=>o.partner_id===PARTNERS[0].id).map(orderView);
  if(m=path.match(/^\/partners\/(.+)\/boxes$/))return ST.boxes.filter(b=>b.partner_id===m[1]).map(boxView);
  if(m=path.match(/^\/partners\/(.+)\/orders$/))return ST.orders.filter(o=>o.partner_id===m[1]).map(orderView);
  if(path==="/admin/stats")return statsCalc();
  if(path==="/admin/orders")return ST.orders.slice().reverse().map(orderView);
  if(path==="/admin/partner-applications")return [];
  if(path==="/admin/refund-requests")return [];
  if(path==="/me/orders")return myDemoOrders();
  if(path==="/me/recommendations")return demoRecommend();
  if(m=path.match(/^\/partners\/(.+)\/reviews$/))
    return (ST.reviews||[]).filter(r=>r.partner_id===m[1]&&r.status==="approved").slice().reverse();
  throw new Error("404 "+path);
}
/* демо-эквиваленты серверных /me/* — «мои» заказы = коды в этом браузере */
function myDemoOrders(){return myCodes().map(c=>ST.orders.find(o=>o.code===c)).filter(Boolean).map(orderView);}
function demoRecommend(limit=4){
  const mine=myDemoOrders(), avail=ST.boxes.filter(b=>b.status==="active"&&b.qty_left>0&&Date.parse(b.pickup_to)>Date.now()).map(boxView);
  if(!mine.length)return avail.slice().sort((a,b)=>Date.parse(a.pickup_to)-Date.parse(b.pickup_to)).slice(0,limit);
  const catCnt={}, partnerCnt={};
  mine.forEach(o=>{catCnt[o.category]=(catCnt[o.category]||0)+1; partnerCnt[o.partner_id]=(partnerCnt[o.partner_id]||0)+1;});
  return avail.slice().sort((a,b)=>{
    const sa=(catCnt[a.category]||0)*2+(partnerCnt[a.partner_id]||0)*3;
    const sb=(catCnt[b.category]||0)*2+(partnerCnt[b.partner_id]||0)*3;
    return sb-sa || Date.parse(a.pickup_to)-Date.parse(b.pickup_to);
  }).slice(0,limit);
}
/* эвристическая модерация — JS-копия app/ai.py:heuristic_moderate (без AI-ключа в браузере) */
function demoModerate(text){
  const t=(text||"").trim();
  if(t.length<3)return[false,"слишком короткий отзыв"];
  const banned=["блять","сука","хуй","пизд","ебан","нахуй","долбоеб","мудак","fuck","shit","asshole","bitch"];
  const low=t.toLowerCase();
  if(banned.some(w=>low.includes(w)))return[false,"недопустимая лексика"];
  if(/(https?:\/\/|www\.|t\.me\/|@\w{4,})/i.test(t))return[false,"похоже на спам-ссылку"];
  const letters=(t.match(/[a-zа-яё]/gi)||[]).length, caps=(t.match(/[A-ZА-ЯЁ]/g)||[]).length;
  if(letters>8&&caps/letters>0.7)return[false,"капслок"];
  if(/(.)\1{6,}/.test(t))return[false,"спам-повтор символов"];
  return[true,""];
}
async function _demoPost(u,body){ let m;
  if(u==="/orders"){const b=ST.boxes.find(x=>x.id===body.box_id);if(!b)throw new Error("Бокс не найден");
    if(Date.parse(b.pickup_to)<=Date.now())throw new Error("Окно выдачи этого бокса уже завершилось");
    if(b.qty_left<=0)throw new Error("Боксы закончились"); b.qty_left--;
    const o={id:"o"+(ST.seq++),code:newCode(),box_id:b.id,partner_id:b.partner_id,category:b.category,price:b.price,
      user_name:body.user_name,user_phone:body.user_phone,status:"paid",pickup_from:b.pickup_from,pickup_to:b.pickup_to,created_at:new Date().toISOString()};
    ST.orders.push(o);persist();return {order:orderView(o),qr_svg:qrSvg(o.code)};}
  if(u==="/boxes"){if(body.value_est<body.price)throw new Error("Ценность должна быть не ниже цены");
    const b={id:"b"+(ST.seq++),partner_id:body.partner_id,category:body.category,title:body.title,price:body.price,
      value_est:body.value_est,qty_total:body.qty,qty_left:body.qty,pickup_from:body.pickup_from,pickup_to:body.pickup_to,
      description:body.description,created_at:new Date().toISOString(),status:"active"};
    ST.boxes.push(b);persist();return boxView(b);}
  if(u==="/redeem"){const o=ST.orders.find(x=>x.code===(body.code||"").trim().toUpperCase());
    if(!o)return{ok:false,message:"Заказ с таким кодом не найден",order:null};
    const st=effStatus(o);
    if(st==="issued")return{ok:false,message:"Этот заказ уже выдан",order:orderView(o)};
    if(st==="refunded"||st==="cancelled")return{ok:false,message:"Заказ отменён/возвращён",order:orderView(o)};
    if(st==="expired")return{ok:false,message:"Окно выдачи истекло (no-show)",order:orderView(o)};
    o.status="issued";persist();return{ok:true,message:"Выдано ✓",order:orderView(o)};}
  if(m=u.match(/^\/admin\/refund\/(.+)$/)){const o=ST.orders.find(x=>x.id===m[1]);
    if(!o||["issued","refunded","cancelled"].includes(o.status))return{refunded:false};
    o.status="refunded";const b=ST.boxes.find(x=>x.id===o.box_id);if(b)b.qty_left++;persist();return{refunded:true};}
  if(u==="/auth/password/forgot")return{status:"accepted"};
  if(u==="/ai/describe-box"){
    if(!body.notes||!body.notes.trim())throw new Error("Опиши, что осталось — хотя бы пару слов");
    const cat=CAT_RU[body.category]||body.category, notes=body.notes.trim().replace(/[.\s]+$/,"");
    const low=cat.charAt(0).toLowerCase()+cat.slice(1);
    return {description:`${low.charAt(0).toUpperCase()+low.slice(1)}: ${notes}. Свежее и вкусное — успей забрать сегодня по акции!`, ai:false};
  }
  if(m=u.match(/^\/partners\/(.+)\/reviews$/)){
    const pid=m[1], order=ST.orders.find(x=>x.id===body.order_id);
    if(!order||order.partner_id!==pid||!myCodes().includes(order.code))throw new Error("Заказ не найден или не принадлежит вам");
    if(effStatus(order)!=="issued")throw new Error("Отзыв можно оставить только после получения заказа");
    if((ST.reviews||[]).some(r=>r.order_id===order.id))throw new Error("Отзыв на этот заказ уже оставлен");
    const [ok,reason]=demoModerate(body.text);
    if(!ok)throw new Error("Отзыв не прошёл модерацию: "+reason);
    const rv={id:"rv"+(ST.seq++),partner_id:pid,order_id:order.id,author_name:order.user_name||"Покупатель",
      rating:body.rating,text:body.text.trim(),status:"approved",created_at:new Date().toISOString()};
    ST.reviews=ST.reviews||[]; ST.reviews.push(rv); persist();
    return rv;
  }
  throw new Error("404 "+u);
}
