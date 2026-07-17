const $=s=>document.querySelector(s);

/* ================= i18n: ҚАЗАҚША / РУССКИЙ =================
   Словарь RU→KZ + MutationObserver: переводит и статичный HTML, и всё,
   что рендерит JS — без переписывания шаблонов. Выбор в localStorage. */
const LANG=localStorage.getItem("ym_lang")||"ru";
const KZ={
"Спасай еду":"Тағамды құтқар","Поиск боксов и заведений":"Бокстар мен мекемелерді іздеу",
"Магазин":"Дүкен","Партнёр":"Серіктес","Админ":"Әкімші","Гость":"Қонақ","Войти":"Кіру",
"Главная":"Басты","Рядом":"Жақын","Заказы":"Тапсырыстар",
"Все":"Барлығы","Сладкое":"Тәтті","Выпечка":"Нан-тоқаш","Снеки":"Снектер","Микс":"Микс",
"Вечерние излишки кофеен — со скидкой до 70%":"Кофеханалардың кешкі артық өнімі — 70%-ға дейін жеңілдікпен",
"Кофейни и пекарни Астаны собирают непроданное за день в сюрприз-боксы. Еда свежая — просто её приготовили сегодня больше, чем купили. Ты экономишь, заведение не списывает.":"Астананың кофеханалары мен наубайханалары күні бойы сатылмағанды сюрприз-бокстарға жинайды. Тағам жаңа — тек бүгін сатылғаннан көбірек дайындалған. Сен үнемдейсің, мекеме шығынға жазбайды.",
"Смотреть боксы":"Бокстарды қарау","☕ Заведения на карте":"☕ Картадағы мекемелер",
"Список":"Тізім","Карта":"Карта","Все районы":"Барлық аудандар",
"⚡ Забрать сейчас":"⚡ Қазір алу","♥ Любимые":"♥ Таңдаулылар","✕ Сбросить":"✕ Тазарту",
"Ничего не нашлось. Попробуй другой район или категорию 🌙":"Ештеңе табылмады. Басқа аудан не санатты көріңіз 🌙",
"Сладкий бокс":"Тәтті бокс","Бокс выпечки":"Нан-тоқаш боксы","Микс-бокс":"Микс-бокс","Снек-бокс":"Снек-бокс",
"Как это работает":"Бұл қалай жұмыс істейді",
"Выбери бокс":"Боксты таңда","Кофейни выкладывают вечерние излишки со скидкой 40–70%.":"Кофеханалар кешкі артық өнімді 40–70% жеңілдікпен шығарады.",
"Оплати онлайн":"Онлайн төле","Получишь код и QR для выдачи. Состав бокса — приятный сюрприз.":"Алу үшін код пен QR аласың. Бокстың құрамы — жағымды сюрприз.",
"Забери сегодня":"Бүгін алып кет","Покажи код на кассе в окно самовывоза — и наслаждайся.":"Кассада кодты өзі алып кету уақытында көрсет — ләззат ал.",
"Цена":"Бағасы","Самовывоз":"Өзі алып кету","Осталось":"Қалғаны","Что обычно внутри:":"Ішінде әдетте:",
"Ваше имя":"Атыңыз","Имя":"Аты","Телефон":"Телефон","Email":"Email","Пароль":"Құпиясөз",
"🔗 Поделиться боксом":"🔗 Бокспен бөлісу","Закрыть":"Жабу","Готово":"Дайын","Отмена":"Бас тарту",
"Бокс забронирован!":"Бокс броньдалды!","Покажите код или QR на кассе.":"Кассада кодты немесе QR-ды көрсетіңіз.",
"Покажите код на кассе.":"Кассада кодты көрсетіңіз.","Забрать:":"Алу уақыты:","Код выдачи":"Беру коды",
"🗺 Маршрут в 2ГИС":"🗺 2ГИС-те бағыт","🗺 Маршрут":"🗺 Бағыт","Мои заказы":"Менің тапсырыстарым",
"Показать код и QR":"Код пен QR көрсету","Не выдали заказ? Вернуть деньги":"Тапсырыс берілмеді ме? Ақшаны қайтару",
"оплачен":"төленді","выдан":"берілді","не забран":"алынбады","возврат":"қайтарым","отменён":"жойылды",
"Заведения рядом":"Маңайдағы мекемелер",
"Кофейни-партнёры Yummy в Астане — выбери район и забери сюрприз-бокс сегодня.":"Yummy серіктес-кофеханалары Астанада — ауданды таңдап, бүгін сюрприз-бокс алып кет.",
"Сегодня боксов нет":"Бүгін бокс жоқ","Доступно сегодня — можно забрать:":"Бүгін қолжетімді — алуға болады:",
"Забрать":"Алу","Ничего не нашлось в этом фильтре.":"Бұл сүзгіде ештеңе табылмады.",
"Есильский":"Есіл","Нура":"Нұра","Сарайшык":"Сарайшық","Байконур":"Байқоңыр","Сарыарка":"Сарыарқа","Алматинский":"Алматы",
"Добро пожаловать 👋":"Қош келдіңіз 👋",
"Спасайте свежую еду из кофеен и пекарен Астаны со скидкой до 70%. Кто вы?":"Астана кофеханалары мен наубайханаларының жаңа тағамын 70%-ға дейін жеңілдікпен құтқарыңыз. Сіз кімсіз?",
"Я покупатель":"Мен сатып алушымын","Бронировать и забирать сюрприз-боксы":"Сюрприз-бокстарды броньдап алып кету",
"Я заведение":"Мен мекеме иесімін","Кофейня/пекарня — продавать вечерние излишки":"Кофехана/наубайхана — кешкі артықты сату",
"Пропустить, просто осмотреться →":"Өткізіп жіберу, жай қарап шығу →","Уже есть аккаунт? Войти":"Аккаунт бар ма? Кіру",
"Создать аккаунт":"Аккаунт құру","Регистрация заведения":"Мекемені тіркеу","Личный кабинет покупателя.":"Сатып алушының жеке кабинеті.",
"Кабинет владельца кофейни или пекарни.":"Кофехана не наубайхана иесінің кабинеті.",
"Название заведения":"Мекеме атауы","Зарегистрироваться":"Тіркелу","Вход":"Кіру",
"Войдите в аккаунт покупателя или заведения.":"Сатып алушы не мекеме аккаунтына кіріңіз.",
"Сменить роль":"Рөлді ауыстыру","Выйти":"Шығу","🔑 Сменить пароль":"🔑 Құпиясөзді ауыстыру",
"Сменить пароль":"Құпиясөзді ауыстыру","Текущий пароль":"Ағымдағы құпиясөз","Новый пароль":"Жаңа құпиясөз","Сохранить":"Сақтау",
"🚪 Выйти со всех устройств":"🚪 Барлық құрылғылардан шығу","⬇ Скачать мои данные":"⬇ Деректерімді жүктеу",
"🗑 Удалить аккаунт":"🗑 Аккаунтты жою","Удалить аккаунт?":"Аккаунтты жою керек пе?",
"Данные заказов обезличатся, вход станет невозможен. Действие необратимо.":"Тапсырыс деректері иесізденеді, кіру мүмкін болмайды. Әрекет қайтарылмайды.",
"Да, удалить":"Иә, жою","Вышли со всех устройств":"Барлық құрылғылардан шықтыңыз",
"Демо-вход (без сервера). Настоящий вход — после деплоя бэкенда":"Демо-кіру (серверсіз). Нақты кіру — бэкенд орналастырылғаннан кейін",
"Данные скачаны ⬇":"Деректер жүктелді ⬇","Аккаунт удалён":"Аккаунт жойылды",
"Кабинет партнёра":"Серіктес кабинеті",
"Выставляй боксы из вечерних остатков за минуту. Выдавай заказы по коду.":"Кешкі қалдықтардан бокстарды бір минутта шығар. Тапсырысты код бойынша бер.",
"Заведение":"Мекеме","Создать бокс":"Бокс құру","Категория":"Санат","Название":"Атауы",
"Опубликовать бокс":"Боксты жариялау","Выдать заказ по коду":"Тапсырысты код бойынша беру","Выдать":"Беру",
"📷 Сканировать QR камерой":"📷 QR-ды камерамен сканерлеу","Мои боксы":"Менің бокстарым","Брони и выдачи":"Броньдар мен берулер",
"Боксов пока нет.":"Әзірге бокс жоқ.","Броней пока нет.":"Әзірге бронь жоқ.",
"выручка с боксов":"бокстардан түскен табыс","выкуп (забрали)":"алып кетті","в продаже":"сатылымда",
"Админ-панель":"Әкімші панелі","Контроль заказов, возвраты, ключевые метрики пилота.":"Тапсырыстарды бақылау, қайтарымдар, пилоттың негізгі метрикалары.",
"Все заказы":"Барлық тапсырыстар","Заказов нет.":"Тапсырыс жоқ.","Возврат":"Қайтару",
"Заказы по статусу":"Тапсырыстар мәртебе бойынша","Выкуп боксов":"Бокстарды алып кету","Выручка по заведениям · топ-5":"Мекемелер бойынша табыс · топ-5",
"GMV (оборот)":"GMV (айналым)","заказов":"тапсырыс","выкуплено (fill rate)":"алынды (fill rate)","не забрали (no-show)":"алынбады (no-show)",
"выдано":"берілді","активных":"белсенді","возвратов":"қайтарым","активные":"белсенді","не забрали":"алынбады","возвраты":"қайтарымдар",
"Частые вопросы":"Жиі қойылатын сұрақтар","Документы":"Құжаттар","Контакты":"Байланыс",
"Что внутри бокса?":"Бокстың ішінде не бар?",
"Пришёл, а заведение закрыто или бокса нет?":"Келдім, бірақ мекеме жабық не бокс жоқ болса?",
"Не успел забрать в окно выдачи?":"Беру уақытында алып үлгермедіңіз бе?",
"Насколько это безопасно?":"Бұл қаншалықты қауіпсіз?",
"Публичная оферта":"Жария оферта","Политика конфиденциальности":"Құпиялылық саясаты",
"Стандарты пищевой безопасности":"Тағам қауіпсіздігі стандарттары","Договор с заведением":"Мекемемен келісім",
"Необходимо согласие с офертой и обработкой данных":"Оферта мен деректерді өңдеуге келісім қажет",
"💬 Telegram-поддержка":"💬 Telegram-қолдау","📲 Установить приложение":"📲 Қосымшаны орнату","Код на GitHub":"GitHub-тағы код",
"Доступ для персонала":"Қызметкерлерге арналған кіру","PIN-код":"PIN-код",
"Сессия входа хранится в защищённых HttpOnly cookies; коды заказов, избранное и фильтры — локально в браузере.":"Кіру сессиясы қорғалған HttpOnly cookie файлдарында, ал тапсырыс кодтары, таңдаулылар мен сүзгілер браузерде жергілікті сақталады.",
"Понятно":"Түсінікті",
"Боксы в Астане":"Астанадағы бокстар","Свежее, дешевле и без списаний.":"Жаңа, арзан және шығынсыз.",
"Не нашли свою кофейню?":"Өз кофеханаңызды таппадыңыз ба?",
"Расскажите — подключим её к Yummy в ближайшую неделю.":"Айтыңыз — оны бір апта ішінде Yummy-ге қосамыз.",
"Предложить заведение":"Мекеме ұсыну",
"Астана · движение против выбрасывания еды":"Астана · тағамды ысырап етпеу қозғалысы",
"Спасай свежую еду из любимых кофеен":"Сүйікті кофеханалардан жаңа тағамды құтқар",
"К вечеру в кофейнях остаётся свежая выпечка. Раньше она отправлялась в мусор — теперь в сюрприз-боксы со скидкой до 70%.":"Кешке қарай кофеханаларда жаңа нан-тоқаш қалады. Бұрын ол қоқысқа кететін — енді 70%-ға дейін жеңілдікпен сюрприз-бокстарға салынады.",
"Как это работает ↓":"Бұл қалай жұмыс істейді ↓",
"еды в мире выбрасывается впустую":"әлемдегі тағам босқа тасталады",
"вечерней выпечки кофейни списывают":"кешкі нан-тоқашты кофеханалар шығынға жазады",
"твоя скидка на спасённый бокс":"құтқарылған боксқа сенің жеңілдігің",
"Три шага до спасённого ужина":"Құтқарылған кешкі асқа үш қадам",
"Покрытие":"Қамту","137 заведений на карте Астаны":"Астана картасында 137 мекеме",
"Zebra Coffee, Espresso Day и другие — фильтруй по районам, выбирай ближайшую точку.":"Zebra Coffee, Espresso Day және басқалар — аудан бойынша сүзіп, ең жақын нүктені таңда.",
"☕ Открыть карту":"☕ Картаны ашу",
"Вы — кофейня или пекарня?":"Сіз кофехана не наубайхана иесісіз бе?",
"Превращайте вечерние списания в выручку. Подключение бесплатно.":"Кешкі шығындарды табысқа айналдырыңыз. Қосылу тегін.",
"Стать партнёром":"Серіктес болу","Присоединяйся":"Қосыл",
"Создай аккаунт за 20 секунд":"20 секундта аккаунт құр",
"Обновляем…":"Жаңартудамыз…","Оплата…":"Төлем…","Входим…":"Кіру…","Создаём аккаунт…":"Аккаунт құрудамыз…",
"Это сюрприз-бокс из свежих остатков дня. В карточке каждого бокса есть примерный состав, но точное наполнение меняется — в этом и смысл выгодной цены.":"Бұл — күннің жаңа қалдықтарынан жасалған сюрприз-бокс. Әр бокстың карточкасында шамамен құрамы көрсетілген, бірақ нақты құрамы өзгеріп тұрады — тиімді бағаның мәні де осында.",
"Нажми «Вернуть деньги» в «Моих заказах» или напиши в поддержку — если заказ не выдан по вине заведения, мы возвращаем полную сумму.":"«Менің тапсырыстарым» бөлімінде «Ақшаны қайтару» батырмасын бас немесе қолдауға жаз — тапсырыс мекеменің кінәсінен берілмесе, толық соманы қайтарамыз.",
"Бронь сгорает, предоплата не возвращается — заведение резервировало бокс под тебя. Пожалуйста, приходи вовремя.":"Бронь күйіп кетеді, алдын ала төлем қайтарылмайды — мекеме боксты сен үшін сақтап қойған. Уақытында келуіңді сұраймыз.",
"Продаётся только свежая еда текущего дня в допустимом окне реализации. Партнёры проходят проверку при подключении и отвечают за качество по стандартам сервиса; самовывоз — только день в день.":"Тек ағымдағы күннің жаңа тағамы рұқсат етілген сату уақытында сатылады. Серіктестер қосылу кезінде тексеруден өтеді және сервис стандарттары бойынша сапаға жауап береді; өзі алып кету — тек сол күні.",
"✨ Тебе понравится":"✨ Саған ұнайды","✨ Улучшить описание с ИИ":"✨ ЖИ көмегімен сипаттаманы жақсарту",
"Загружаем отзывы…":"Пікірлерді жүктеп жатырмыз…",
"Отзывы покупателей — только по подтверждённым заказам":"Сатып алушы пікірлері — тек расталған тапсырыстар бойынша",
"Реальных отзывов пока нет — вот примеры того, как это будет выглядеть (демо):":"Нақты пікірлер әлі жоқ — бұл қалай көрінетінінің мысалдары (демо):",
"⭐ Оставить отзыв":"⭐ Пікір қалдыру","Комментарий":"Пікір","Что понравилось или нет?":"Не ұнады, не ұнамады?",
"Отправить отзыв":"Пікірді жіберу","Напишите пару слов":"Бір-екі сөз жазыңыз","Отправляем…":"Жіберудеміз…",
"Спасибо за отзыв! ⭐":"Пікіріңізге рахмет! ⭐",
"Сначала напиши черновик — хотя бы пару слов":"Алдымен қара жоба жаз — кем дегенде бір-екі сөз",
"Генерирую…":"Жасап жатырмын…",
"Описание улучшено ИИ ✨":"Сипаттама ЖИ көмегімен жақсартылды ✨",
"Описание собрано по шаблону (демо-режим без AI-ключа)":"Сипаттама үлгі бойынша құрастырылды (AI кілтісіз демо-режим)",
};
const KZ_RX=[
[/^Отзыв о (.+)$/,"$1 туралы пікір"],
[/Сегодня/g,"Бүгін"],
[/(Есильский|Алматинский|Сарыарка) р-н/g,(m,d)=>(({"Есильский":"Есіл","Алматинский":"Алматы","Сарыарка":"Сарыарқа"})[d]+" ауданы")],
[/^Боксы рядом( \(\d+\))?$/,"Жақын бокстар$1"],
[/^Бүгін доступно (\d+) бокс(?:а|ов)?$/,"Бүгін $1 бокс қолжетімді"],
[/^(🔥 )?осталось (\d+)$/,"$1қалды: $2"],
[/^осталось (\d+) из (\d+)$/,"қалғаны: $1 / $2"],
[/^(\d+) из (\d+)$/,"$1 / $2"],
[/^Оплатить ([\d\s ]+₸)$/,"Төлеу — $1"],
[/^Заведения( · \d+)?$/,"Мекемелер$1"],
[/^Все сети · (\d+)$/,"Барлық желілер · $1"],
[/^Все районы( · \d+)?$/,"Барлық аудандар$1"],
[/^(Есильский|Нура|Сарайшык|Байконур|Сарыарка|Алматинский) · (\d+)$/,(m,d,n)=>`${KZ[d]||d} · ${n}`],
[/^(\d+) бокс(?:а|ов)?$/,"$1 бокс"],
[/^от ([\d\s ]+₸)$/,"$1-ден"],
[/^(\d+) заведени(?:е|я|й)$/,"$1 мекеме"],
[/^(\d+) (?:продажа|продажи|продаж)$/,"$1 сатылым"],
[/^(\d+) бокс(?:а|ов)? в продаже$/,"сатылымда $1 бокс"],
[/^(\d+) (?:заказ|заказа|заказов)$/,"$1 тапсырыс"],
[/^(\d+) бокс(?:|а|ов) доступ(?:ен|но) к самовывозу сегодня вечером\. Свежее, дешевле и без списаний\.$/,"Бүгін кешке өзі алып кетуге $1 бокс қолжетімді. Жаңа, арзан және шығынсыз."],
];
function kzText(s){
  const t=s.trim(); if(!t)return s;
  if(KZ[t]!==undefined)return s.replace(t,KZ[t]);
  let out=t;
  for(const [re,rep] of KZ_RX){ if(re.test(out)){ out=out.replace(re,rep); re.lastIndex=0; } }
  return out!==t?s.replace(t,out):s;
}
function translateTree(root){
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  let n; while((n=w.nextNode())){ const v=kzText(n.data); if(v!==n.data)n.data=v; }
  if(root.querySelectorAll)root.querySelectorAll("[placeholder],[aria-label],[title]").forEach(el=>{
    for(const at of ["placeholder","aria-label","title"]){const v=el.getAttribute(at); if(v&&KZ[v])el.setAttribute(at,KZ[v]);}
  });
}
if(LANG==="kz"){
  document.documentElement.lang="kk";
  new MutationObserver(muts=>{ for(const m of muts){
    if(m.type==="characterData"){const v=kzText(m.target.data); if(v!==m.target.data)m.target.data=v; continue;}
    m.addedNodes.forEach(nd=>{ if(nd.nodeType===3){const v=kzText(nd.data); if(v!==nd.data)nd.data=v;} else if(nd.nodeType===1)translateTree(nd); });
  }}).observe(document.body,{childList:true,subtree:true,characterData:true});
  translateTree(document.body);
}
{ const lb=$("#langBtn"); lb.textContent=LANG==="kz"?"РУС":"ҚАЗ";
  lb.onclick=()=>{ localStorage.setItem("ym_lang",LANG==="kz"?"ru":"kz"); location.reload(); }; }
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money=n=>Number(n).toLocaleString("ru-RU",{maximumFractionDigits:0})+" ₸";
const hhmm=iso=>{try{return new Date(iso).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"});}catch(e){return "—";}};
const win=(a,b)=>`Сегодня ${hhmm(a)}–${hhmm(b)}`;
const plural=(n,f)=>{const m10=n%10,m100=n%100;return f[(m10===1&&m100!==11)?0:(m10>=2&&m10<=4&&(m100<10||m100>=20))?1:2];};
function toast(m,err=false){const t=$("#toast");t.textContent=m;t.className=err?"err show":"show";clearTimeout(t._t);t._t=setTimeout(()=>t.className="",2800);}
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
/* GitHub Pages: изолированный browser-only store, без production API/cookies. */
const API_BASE = "";
const get=u=>_demoGet(u);
const post=(u,b)=>_demoPost(u,b);
const api=(m,u,b)=>m==="GET"?_demoGet(u):_demoPost(u,b);
const STATUS_RU={payment_pending:"ожидает оплату",paid:"оплачен",issued:"выдан",expired:"не забран",payment_failed:"оплата не прошла",refunded:"возврат",cancelled:"отменён"};
let APP_CONFIG={payment_mode:"demo",payments_enabled:false,production:false,currency:"kzt"};
function applyEnvironmentVisibility(){
  document.querySelectorAll(".demo-only").forEach(el=>el.classList.toggle("hidden",!!APP_CONFIG.production));
}
/* Kaspi Pay deep-link: после регистрации мерчанта в Kaspi Pay вставь свой
   service_id — в модалке оплаты появится настоящая кнопка Kaspi. */
const KASPI_SERVICE_ID="";
/* маршрут в 2ГИС: поиск по названию+адресу (работает без API-ключа) */
const gisUrl=(name,addr)=>"https://2gis.kz/astana/search/"+encodeURIComponent(name+" "+addr);
/* эко-вклад: ~0.5 кг еды и ~1.3 кг CO₂ на бокс (усреднённая оценка food waste) */
const ECO_KG=0.5, ECO_CO2=1.3;
const CATS=[["all","Все","🔥"],["sweet","Сладкое","🍩"],["bakery","Выпечка","🥐"],["snack","Снеки","🥪"],["mixed","Микс","🧺"]];
const REVIEWS={
 "Coffee Point":[["Айгерим","Бокс превзошёл ожидания — 2 пончика и маффин, всё свежее!",5],["Дамир","Хорошая выгода, но приходите к началу окна выдачи.",4]],
 "Bake House":[["Салтанат","Круассаны как утром! Беру второй раз.",5],["Ержан","Нормально за свою цену.",4]],
 "Donut Lab":[["Мария","6 пончиков за 790 — это подарок 🍩",5],["Алекс","Вкусно, глазурь чуть подтаяла.",4]],
 "Сдоба":[["Гульнара","Микс порадовал: сэндвич + выпечка.",5],["Тимур","Сюрприз есть сюрприз — мне попалось всё сладкое.",4]],
 "Sweet Corner":[["Дана","Чизкейк в боксе — любовь!",5],["Арман","Десерты свежие, рекомендую.",5]],
 "Утром Кофе":[["Инкар","Отличная выпечка по вечерней цене.",5],["Санжар","Всё чётко по коду выдали.",4]],
};
let curDistrict="all", curCat="all", curQuery="", curNow=false, curFav=false, mapMode=false, mapObj=null;
const favs=()=>{try{return JSON.parse(localStorage.getItem("ym_favs")||"[]");}catch(e){return [];}};
window.toggleFav=pid=>{let f=favs();f=f.includes(pid)?f.filter(x=>x!==pid):[...f,pid];
  localStorage.setItem("ym_favs",JSON.stringify(f));renderBoxes();toast(f.includes(pid)?"Кофейня в избранном ♥":"Убрано из избранного");};
/* фильтры переживают перезагрузку */
try{const f=JSON.parse(localStorage.getItem("ym_filters")||"{}");curDistrict=f.d||"all";curCat=f.c||"all";curNow=!!f.n;curFav=!!f.f;}catch(e){}
const saveFilters=()=>localStorage.setItem("ym_filters",JSON.stringify({d:curDistrict,c:curCat,n:curNow,f:curFav}));

/* ---- роли + bottom-nav + демо-доступ персонала ---- */
const roleBtns=[...document.querySelectorAll(".roles button")];
const navBtns=[...document.querySelectorAll(".bnav button")];
function requireStaff(cb){
  const a=account();
  if(a&&a.server&&(a.role==="partner"||a.role==="admin")){cb();return;}
  toast("Доступ только по персональному приглашению",true);
  openLogin();
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

/* CSP-safe event delegation: HTML/templates содержат data-action, не JS-код. */
document.addEventListener("click",e=>{
  const el=e.target.closest?.("[data-action]"); if(!el)return;
  e.preventDefault(); e.stopPropagation();
  const d=el.dataset;
  switch(d.action){
    case "close": closeModal(); break;
    case "goto-orders": gotoOrders(); break;
    case "guest-store": onbGuest(); switchView("store"); break;
    case "guest-venues": onbGuest(); switchView("venues"); break;
    case "scroll-how": $("#l-how").scrollIntoView({behavior:"smooth"}); break;
    case "land-role": landRole(d.role); break;
    case "legal": showLegal(d.key); break;
    case "open-login": openLogin(); break;
    case "scroll-boxes": scrollToBoxes(); break;
    case "switch-view": switchView(d.view); break;
    case "toast": toast(d.message); break;
    case "acct-orders": closeModal(); gotoOrders(); break;
    case "change-password": changePwForm(); break;
    case "logout-all": logoutAll(); break;
    case "export-me": exportMe(); break;
    case "delete-me": deleteMeConfirm(); break;
    case "switch-role": closeModal(); showOnboarding(); break;
    case "logout": logout(); break;
    case "onb-buyer": onbBuyer(); break;
    case "login-form": loginForm(); break;
    case "onb-guest": onbGuest(); break;
    case "show-onboarding": showOnboarding(); break;
    case "toggle-fav": toggleFav(d.partnerId); break;
    case "reviews": showReviews(d.partnerId,d.name); break;
    case "shop-map": shopFromMap(d.name); break;
    case "open-venue": openVenue(d.id); break;
    case "book-venue": bookVenueBox(d.id,+d.index); break;
    case "close-load-venues": closeModal(); loadVenues(); break;
    case "support-refund": refundRequestForm(d.id); break;
    case "leave-review": leaveReviewForm(d.orderId,d.partnerId,d.name); break;
    case "show-code": showCode(d.code); break;
    case "refund": refund(d.id); break;
    case "partner-status": setPartnerStatus(d.id,d.status); break;
    case "verify-email": verifyEmailManually(d.id); break;
    case "refund-decision": decideRefund(d.id,d.actionValue); break;
    case "request-verification": requestVerification(); break;
    case "forgot-password": forgotPasswordForm(); break;
  }
},true);

/* ============ АККАУНТ / ОНБОРДИНГ ============ */
const ROLE_RU={buyer:"Покупатель",partner:"Заведение",guest:"Гость"};
function safeAccount(a){return a?{v:3,role:a.role,name:a.name,server:!!a.server,emailVerified:!!a.emailVerified,createdAt:a.createdAt||Date.now()}:null;}
function account(){try{const a=JSON.parse(localStorage.getItem("ym_account")||"null"),safe=safeAccount(a);
  if(a&&a.v!==3)localStorage.setItem("ym_account",JSON.stringify(safe));return safe;}catch(e){return null;}}
function setAccount(a){const safe=safeAccount(a);if(safe)localStorage.setItem("ym_account",JSON.stringify(safe));else localStorage.removeItem("ym_account");renderAccount();}
function applyRoleVisibility(){
  const role=account()?.role;
  document.querySelectorAll(".staff-nav").forEach(el=>el.classList.toggle("hidden",role!=="partner"));
  document.querySelectorAll(".admin-nav").forEach(el=>el.classList.toggle("hidden",role!=="admin"));
}
function renderAccount(){
  applyRoleVisibility();
  const a=account(), btn=$("#acctBtn");
  if(!a){btn.innerHTML='<span class="av">?</span><span class="nm">Войти</span>';btn.onclick=showOnboarding;return;}
  const ini=((a.name||"?").trim()[0]||"?").toUpperCase();
  btn.innerHTML=`<span class="av">${esc(ini)}</span><span class="nm">${esc(a.name||ROLE_RU[a.role])}</span>`;
  btn.onclick=acctMenu;
}
function acctMenu(){
  const a=account()||{};
  showModal(`<div class="mc">
    <h3>${esc(a.name||"Профиль")}</h3>
    <p style="color:var(--txt2);font-size:.85rem;margin:.1rem 0 .9rem">Вы вошли как <b style="color:var(--brown)">${ROLE_RU[a.role]||"гость"}</b></p>
    <button class="btn" data-action="acct-orders">🛒 Мои заказы</button>
    ${a.server&&!a.emailVerified?`<p style="color:var(--red);font-size:.8rem">Email не подтверждён</p><button class="btn sec" data-action="request-verification">✉ Отправить подтверждение</button>`:""}
    ${a.server?`<button class="btn sec" style="margin-top:.5rem" data-action="change-password">🔑 Сменить пароль</button>
    <button class="btn sec" style="margin-top:.5rem" data-action="logout-all">🚪 Выйти со всех устройств</button>
    <button class="btn sec" style="margin-top:.5rem" data-action="export-me">⬇ Скачать мои данные</button>
    <button class="btn sec" style="margin-top:.5rem;color:var(--red)" data-action="delete-me">🗑 Удалить аккаунт</button>`:""}
    <button class="btn sec" style="margin-top:.5rem" data-action="switch-role">Сменить роль</button>
    <button class="btn sec" style="margin-top:.5rem" data-action="logout">Выйти</button>
  </div>`);
}
/* Privacy + сессии (Sentinel-паттерны, реализованные честно) */
window.logoutAll=async()=>{
  try{await post("/session/logout-all");}catch(e){toast(e.message,true);return;}
  toast("Вышли со всех устройств"); logout(false);
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
    <button class="btn sec" data-action="close" style="margin-top:.5rem">Отмена</button>
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
    <button class="btn sec" data-action="close" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#pwBtn").onclick=async()=>{
    const old=$("#pwOld").value, nw=$("#pwNew").value;
    const pe=_pwErr(nw); if(pe){$("#pw_err").textContent=pe;return;}
    try{ await post("/session/change-password",{old_password:old,new_password:nw});
      closeModal(); toast("Пароль изменён ✓ Остальные устройства разлогинены"); }
    catch(e){ $("#pw_err").textContent=e.message; }
  };
};
window.requestVerification=async()=>{
  try{await post("/auth/email/verify/request");toast("Если email-доставка настроена, письмо отправлено");}
  catch(e){toast(e.message,true);}
};
window.forgotPasswordForm=()=>{
  showModal(`<div class="mc"><h3>Сброс пароля</h3><label>Email <input id="forgotEmail" type="email" autocomplete="email" /></label><button class="btn" id="forgotBtn" style="margin-top:.6rem">Отправить ссылку</button><button class="btn sec" data-action="close">Отмена</button></div>`);
  $("#forgotBtn").onclick=async()=>{const email=$("#forgotEmail").value.trim();if(!_emailOk(email))return;
    try{await post("/auth/password/forgot",{email});closeModal();toast("Если аккаунт существует, инструкция отправлена");}catch(e){toast(e.message,true);}};
};
function resetPasswordForm(token){
  showModal(`<div class="mc"><h3>Новый пароль</h3><label>Пароль <input id="resetPass" type="password" autocomplete="new-password" /><span class="ferr" id="resetErr"></span></label><button class="btn" id="resetBtn" style="margin-top:.6rem">Сохранить</button></div>`);
  $("#resetBtn").onclick=async()=>{const password=$("#resetPass").value,err=_pwErr(password);if(err){$("#resetErr").textContent=err;return;}
    try{await post("/auth/password/reset",{token,new_password:password});closeModal();await logout();toast("Пароль изменён — войдите заново");}catch(e){$("#resetErr").textContent=e.message;}};
}

async function logout(remote=true){
  const a=account();
  if(remote&&a&&a.server){try{await post("/session/logout");}catch(e){}}
  localStorage.removeItem("ym_account");sessionStorage.removeItem("ym_staff");
  closeModal();renderAccount();switchView("store");showOnboarding();
}
function hideOnboarding(){$("#onboard").className="hidden";$("#onboard").innerHTML="";}
function showOnboarding(){
  const o=$("#onboard");o.className="onb";
  o.innerHTML=`<div class="onb-card">
    <div class="onb-logo"><img src="img/logo.png" alt=""><b>Yummy</b></div>
    <h2>Добро пожаловать 👋</h2>
    <p class="lead">Спасайте свежую еду из кофеен и пекарен Астаны со скидкой до 70%. Кто вы?</p>
    <button class="role-card" data-action="onb-buyer"><span class="ic">🛍️</span><div><div class="t">Я покупатель</div><div class="d">Бронировать и забирать сюрприз-боксы</div></div></button>
    <button class="guest" data-action="login-form">Уже есть аккаунт? Войти</button>
    <button class="guest" data-action="onb-guest">Пропустить, просто осмотреться →</button>
  </div>`;
}
/* Вход по email+паролю → HttpOnly cookie session; токены JS не получает. */
function loginForm(){
  const o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <button class="onb-back" data-action="show-onboarding">← Назад</button>
    <h2>Вход</h2>
    <p class="lead">Войдите в аккаунт покупателя или заведения.</p>
    <label>Email <input id="lgEmail" type="email" placeholder="you@email.com" autocomplete="email" /><span class="ferr" id="le_email"></span></label>
    <label>Пароль <span class="pw"><input id="lgPass" type="password" autocomplete="current-password" />
      <button type="button" class="pw-t" id="lgToggle" aria-label="Показать пароль">👁</button></span><span class="ferr" id="le_pass"></span></label>
    <label>MFA / recovery-код <input id="lgMfa" autocomplete="one-time-code" maxlength="20" placeholder="Только для администратора" /></label>
    <button class="btn" id="lgBtn" style="margin-top:.5rem">Войти</button>
    <button class="guest" data-action="forgot-password">Забыли пароль?</button>
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
      const mfa=$("#lgMfa").value.trim();
      const res=await post("/session/login",{email,password:pass,...(mfa?{mfa_code:mfa}:{})});
      const u=res.user, roleMap={customer:"buyer",partner:"partner",admin:"admin"};
      const acc={role:roleMap[u.role]||"buyer",name:u.brand_name||email.split("@")[0],
        server:true,emailVerified:!!u.email_verified,createdAt:Date.now()};
      setAccount(acc);
      if(u.role==="partner"||u.role==="admin")sessionStorage.setItem("ym_staff","1");
      hideOnboarding();
      toast(`С возвращением${acc.name?", "+acc.name:""}!`);
      switchView(u.role==="partner"?"partner":u.role==="admin"?"admin":"store");
    }catch(e){
      if(/404|Failed|fetch|NetworkError|Load failed/i.test(e.message)){
        // статичная демо-версия: настоящего входа нет (нет сервера/пароля) —
        // мягко пускаем в демо-профиль вместо тупика
        setAccount({role:"buyer",name:email.split("@")[0],server:false,createdAt:Date.now()});
        hideOnboarding(); toast("Демо-вход (без сервера). Настоящий вход — после деплоя бэкенда");
        switchView("store"); return;
      }
      $("#le_pass").textContent=e.message;  // реальный бэкенд: «Неверный email или пароль» и т.п.
      btn.disabled=false; btn.textContent="Войти";
    }
  };
}
const _emailOk=v=>/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
const _pwErr=v=>v.length<8?"Минимум 8 символов":(!/[a-zа-яA-ZА-Я]/.test(v)||!/[0-9]/.test(v))?"Нужны буквы и цифры":"";
/* Регистрация: пробуем same-origin cookie session; на статике Pages —
   локальный фолбэк (пароль в браузере НЕ храним). */
async function tryRegister(payload){
  try{ return {mode:"server",res:await post("/session/register",payload)}; }
  catch(e){
    // Локальный профиль допустим только в явно собранной Pages-демке. Ошибки
    // живого API (422/429/500/network) нельзя маскировать успешной регистрацией.
    if(typeof API_BASE!=="undefined"&&API_BASE==="")return {mode:"local"};
    throw e;
  }
}
function onbBuyer(){ regForm("buyer"); }
function onbPartner(){ regForm("partner"); }
function regForm(role){
  const partner=role==="partner", o=$("#onboard");
  o.innerHTML=`<div class="onb-card">
    <button class="onb-back" data-action="show-onboarding">← Назад к выбору роли</button>
    <h2>${partner?"Регистрация заведения":"Создать аккаунт"}</h2>
    <p class="lead">${partner?"Кабинет владельца кофейни или пекарни.":"Личный кабинет покупателя."}</p>
    ${partner
      ?`<label>Название заведения <input id="rgName" placeholder="Напр.: Coffee Point" autocomplete="organization" /><span class="ferr" id="e_name"></span></label>
         <label>Адрес заведения <input id="rgAddress" placeholder="Напр.: пр. Мангилик Ел, 55" autocomplete="street-address" /><span class="ferr" id="e_address"></span></label>
         <label>Район <select id="rgDistrict"><option>Есильский р-н</option><option>Нура р-н</option><option>Алматинский р-н</option><option>Сарыарка р-н</option><option>Байконур р-н</option><option>Сарайшык р-н</option></select></label>`
      :`<label>Имя <input id="rgName" placeholder="Как к вам обращаться" autocomplete="name" /><span class="ferr" id="e_name"></span></label>`}
    <label>Email <input id="rgEmail" type="email" placeholder="you@email.com" autocomplete="email" /><span class="ferr" id="e_email"></span></label>
    <label>Пароль <span class="pw"><input id="rgPass" type="password" placeholder="Минимум 8 символов, буквы и цифры" autocomplete="new-password" />
      <button type="button" class="pw-t" id="pwToggle" aria-label="Показать пароль">👁</button></span><span class="ferr" id="e_pass"></span></label>
    <label class="consent"><input type="checkbox" id="rgConsent" />
      <span>Принимаю <a data-action="legal" data-key="offer">оферту</a> и даю согласие на обработку персональных данных согласно <a data-action="legal" data-key="privacy">политике</a>.${partner?` Принимаю <a data-action="legal" data-key="agreement">договор</a> и <a data-action="legal" data-key="quality">стандарты пищевой безопасности</a>.`:""}</span></label>
    <span class="ferr" id="e_consent"></span>
    <button class="btn" id="rgBtn" style="margin-top:.4rem">Зарегистрироваться</button>
  </div>`;
  $("#rgName").focus();
  $("#pwToggle").onclick=()=>{const p=$("#rgPass");p.type=p.type==="password"?"text":"password";};
  $("#rgBtn").onclick=async()=>{
    const setE=(id,m)=>$("#"+id).textContent=m||"";
    ["e_name","e_email","e_pass","e_address"].forEach(id=>{if($("#"+id))setE(id,"");});
    const name=$("#rgName").value.trim(), email=$("#rgEmail").value.trim(), pass=$("#rgPass").value;
    const address=partner?$("#rgAddress").value.trim():"";
    let bad=false;
    if(name.length<2){setE("e_name",partner?"Укажите название заведения":"Введите имя");bad=true;}
    if(partner&&!address){setE("e_address","Укажите адрес точки");bad=true;}
    if(!_emailOk(email)){setE("e_email","Некорректный email");bad=true;}
    const pe=_pwErr(pass); if(pe){setE("e_pass",pe);bad=true;}
    if(!$("#rgConsent").checked){setE("e_consent","Необходимо согласие с офертой и обработкой данных");bad=true;}
    if(bad)return;
    const btn=$("#rgBtn"); btn.disabled=true; btn.textContent="Создаём аккаунт…";
    try{
      const payload=partner
        ?{email,password:pass,role:"partner",brand_name:name,address,district:$("#rgDistrict").value,accepted_terms:true}
        :{email,password:pass,role:"customer",accepted_terms:true};
      let out;
      try{ out=await tryRegister(payload); }
      catch(e){ setE("e_email",e.message); btn.disabled=false; btn.textContent="Зарегистрироваться"; return; }
      const acc={role:partner?"partner":"buyer",name,createdAt:Date.now(),server:out.mode==="server",emailVerified:!!out.res?.user?.email_verified};
      setAccount(acc);
      if(partner)sessionStorage.setItem("ym_staff","1");   // регистрация партнёра = доступ к кабинету
      hideOnboarding();
      toast(out.mode==="server"?"Аккаунт создан ✓":"Профиль создан (демо). Добро пожаловать!");
      switchView(partner?"partner":"store");
    }catch(e){ toast(e.message,true); btn.disabled=false; btn.textContent="Зарегистрироваться"; }
  };
}
function onbGuest(){setAccount({role:"guest",name:"Гость",createdAt:Date.now()});hideOnboarding();}

/* ============ ЛЕНДИНГ: инлайн-регистрация + reveal-анимации ============ */
window.openLogin=()=>{$("#onboard").className="onb";loginForm();};
window.__landRole="buyer";
window.landRole=r=>{
  window.__landRole=r;
  $("#lr-buyer").classList.toggle("on",r==="buyer");
  $("#lr-partner")?.classList.toggle("on",r==="partner");
  $("#lrNameL").textContent=r==="partner"?"Название заведения":"Имя";
  $("#lrName").placeholder=r==="partner"?"Напр.: Coffee Point":"Как к вам обращаться";
  $("#lrPartnerFields").classList.toggle("hidden",r!=="partner");
};
$("#lrT").onclick=()=>{const p=$("#lrPass");p.type=p.type==="password"?"text":"password";};
$("#lrBtn").onclick=async()=>{
  const partner=window.__landRole==="partner";
  const setE=(id,m)=>$("#"+id).textContent=m||"";
  ["lr_name","lr_email","lr_pass","lr_address"].forEach(id=>setE(id,""));
  const name=$("#lrName").value.trim(), email=$("#lrEmail").value.trim(), pass=$("#lrPass").value;
  const address=partner?$("#lrAddress").value.trim():"";
  let bad=false;
  if(name.length<2){setE("lr_name",partner?"Укажите название заведения":"Введите имя");bad=true;}
  if(partner&&!address){setE("lr_address","Укажите адрес точки");bad=true;}
  if(!_emailOk(email)){setE("lr_email","Некорректный email");bad=true;}
  const pe=_pwErr(pass); if(pe){setE("lr_pass",pe);bad=true;}
  if(!$("#lrConsent").checked){setE("lr_consent","Необходимо согласие с офертой и обработкой данных");bad=true;}
  if(bad)return;
  const btn=$("#lrBtn"); btn.disabled=true; btn.textContent="Создаём аккаунт…";
  try{
    const payload=partner
      ?{email,password:pass,role:"partner",brand_name:name,address,district:$("#lrDistrict").value,accepted_terms:true}
      :{email,password:pass,role:"customer",accepted_terms:true};
    let out;
    try{ out=await tryRegister(payload); }
    catch(e){ setE("lr_email",e.message); btn.disabled=false; btn.textContent="Зарегистрироваться"; return; }
    const acc={role:partner?"partner":"buyer",name,createdAt:Date.now(),server:out.mode==="server",emailVerified:!!out.res?.user?.email_verified};
    setAccount(acc);
    if(partner)sessionStorage.setItem("ym_staff","1");
    toast(out.mode==="server"?"Аккаунт создан ✓":"Профиль создан (демо). Добро пожаловать!");
    switchView(partner?"partner":"store");
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
  if(!demoMode&&!(a&&a.server)){wrap.classList.add("hidden");return;}
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
    <div class="top" style="background-image:url(img/${imgFor(b)})">
      <span class="bdg b-disc">${b.emoji} −${b.discount}%</span>
      <span class="bdg b-left${fomo?" fomo":""}">${fomo?"🔥 ":""}осталось ${b.qty_left}</span>
      <button class="b-fav${favs().includes(b.partner_id)?" on":""}" title="Любимая кофейня"
        data-action="toggle-fav" data-partner-id="${esc(b.partner_id)}">♥</button></div>
    <div class="body">
      <div class="trow"><h3>${esc(b.title||b.partner_name)}</h3>
        <button class="rt" data-action="reviews" data-partner-id="${esc(b.partner_id)}" data-name="${esc(b.partner_name)}">⭐ ${b.rating}</button></div>
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
    mapObj._icon=L.icon({iconUrl:"img/logo.png",iconSize:[34,34],iconAnchor:[17,34],popupAnchor:[0,-30]});
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
      ${n?`<button data-action="shop-map" data-name="${esc(p.name)}" style="width:100%;background:oklch(22% .03 45);border:0;padding:8px;border-radius:999px;font-weight:700;color:oklch(97% .018 82);cursor:pointer;font-family:inherit">Смотреть боксы</button>`:'<span style="font-size:.74rem;color:#7E6A5A">Сегодня боксов нет</span>'}
      <a href="https://2gis.kz/astana/directions/points/%7C${p.lng}%2C${p.lat}" target="_blank" rel="noopener"
        style="display:block;text-align:center;margin-top:6px;font-size:.76rem;font-weight:700;color:#653624">🗺 Маршрут в 2ГИС</a>
    </div>`;
    return L.marker([p.lat,p.lng],{icon:mapObj._icon,title:p.name}).addTo(mapObj).bindPopup(html);
  });
}
window.shopFromMap=name=>{
  curQuery=name.toLowerCase();
  ["q","qm"].forEach(id=>{const e=$("#"+id);if(e)e.value=name;});
  $("#vList").click();                                     // назад в список
  renderBoxes();
  setTimeout(()=>$("#boxes").scrollIntoView({behavior:"smooth"}),150);
};

/* ============ ЗАВЕДЕНИЯ (137 точек Zebra/Espresso Day из 2GIS) ============ */
let ALL_VENUES=null, curChain="all", curVDist="all", vmapObj=null, vmapMode=false;
const CHAIN_META={"Espresso Day":{cls:"esp",ic:"☕"},"Zebra Coffee":{cls:"zeb",ic:"🦓"}};
async function fetchVenues(){
  if(ALL_VENUES)return ALL_VENUES;
  for(const u of ["venues.json","venues.json"]){
    try{const r=await fetch(u); if(r.ok){ALL_VENUES=await r.json(); return ALL_VENUES;}}catch(e){}
  }
  ALL_VENUES=[]; return ALL_VENUES;
}
const vBoxCount=v=>v.boxes.reduce((s,b)=>s+b.qty,0);
const vMinPrice=v=>Math.min(...v.boxes.map(b=>b.price));
async function loadVenues(){
  const vs=await fetchVenues();
  // фильтр по сети
  const chains=[...new Set(vs.map(v=>v.chain))];
  $("#chainFilter").innerHTML=[`<button class="${curChain==="all"?"on":""}" data-c="all">Все сети · ${vs.length}</button>`]
    .concat(chains.map(c=>`<button class="${curChain===c?"on":""}" data-c="${esc(c)}">${CHAIN_META[c]?.ic||""} ${esc(c)} · ${vs.filter(v=>v.chain===c).length}</button>`)).join("");
  document.querySelectorAll("#chainFilter button").forEach(b=>b.onclick=()=>{curChain=b.dataset.c;loadVenues();});
  // районы с počтом
  let pool=curChain==="all"?vs:vs.filter(v=>v.chain===curChain);
  const dists=[...new Set(pool.map(v=>v.district))].sort((a,b)=>pool.filter(v=>v.district===b).length-pool.filter(v=>v.district===a).length);
  $("#vDistricts").innerHTML=[`<button class="dist${curVDist==="all"?" on":""}" data-d="all">Все районы · ${pool.length}</button>`]
    .concat(dists.map(d=>`<button class="dist${curVDist===d?" on":""}" data-d="${esc(d)}">${esc(d)} · ${pool.filter(v=>v.district===d).length}</button>`)).join("");
  document.querySelectorAll("#vDistricts .dist").forEach(b=>b.onclick=()=>{curVDist=b.dataset.d;loadVenues();});
  renderVenues();
  if(vmapMode)renderVMap();
}
function venuesFiltered(){
  let vs=ALL_VENUES||[];
  if(curChain!=="all")vs=vs.filter(v=>v.chain===curChain);
  if(curVDist!=="all")vs=vs.filter(v=>v.district===curVDist);
  return vs;
}
function vCard(v){
  const m=CHAIN_META[v.chain]||{cls:"",ic:"☕"}, n=vBoxCount(v);
  const fomo=n<=3;
  return `<article class="vcard" data-id="${v.id}">
    <div class="logo ${m.cls}">${m.ic}</div>
    <div class="b">
      <h3>${esc(v.chain)}</h3>
      <div class="addr">${esc(v.addr)} · ${esc(v.district)}</div>
      <div class="meta">
        ${v.rating?`<span class="star">⭐ ${v.rating}</span>`:""}
        <span class="pill${fomo?"":" gr"}">${fomo?"🔥 ":""}${n} ${plural(n,["бокс","бокса","боксов"])}</span>
        <span class="pill gr">от ${money(vMinPrice(v))}</span>
      </div>
    </div></article>`;
}
function renderVenues(){
  const vs=venuesFiltered();
  $("#vTitle").textContent=`Заведения${vs.length?` · ${vs.length}`:""}`;
  const list=$("#venueList");
  if(!vs.length){list.innerHTML='<p class="vempty">Ничего не нашлось в этом фильтре.</p>';return;}
  if(curVDist!=="all"){ list.innerHTML=vs.map(vCard).join(""); }
  else{ // группировка по районам
    const byD={}; vs.forEach(v=>{(byD[v.district]=byD[v.district]||[]).push(v);});
    const order=Object.keys(byD).sort((a,b)=>byD[b].length-byD[a].length);
    list.style.display="block";
    list.innerHTML=order.map(d=>`<div class="vgroup-h"><h3>${esc(d)}</h3><span>${byD[d].length} ${plural(byD[d].length,["заведение","заведения","заведений"])}</span></div>
      <div class="venues" style="margin-bottom:.4rem">${byD[d].map(vCard).join("")}</div>`).join("");
  }
  if(curVDist!=="all"){list.style.display="grid";}
  document.querySelectorAll(".vcard").forEach(el=>el.onclick=()=>openVenue(el.dataset.id));
}
$("#vvList").onclick=()=>{vmapMode=false;$("#vvList").classList.add("on");$("#vvMap").classList.remove("on");$("#vmap").classList.add("hidden");$("#venueList").classList.remove("hidden");};
$("#vvMap").onclick=()=>{vmapMode=true;$("#vvMap").classList.add("on");$("#vvList").classList.remove("on");$("#venueList").classList.add("hidden");$("#vmap").classList.remove("hidden");renderVMap();};
function renderVMap(){
  const vs=venuesFiltered();
  if(!vmapObj){
    vmapObj=L.map("vmap").setView([51.13,71.43],11);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(vmapObj);
  }
  setTimeout(()=>vmapObj.invalidateSize(),80);
  if(vmapObj._mk)vmapObj._mk.forEach(m=>m.remove());
  vmapObj._mk=vs.map(v=>{
    const color=v.chain==="Zebra Coffee"?"#2b2b2b":"#6F4E37";
    const mk=L.circleMarker([v.lat,v.lon],{radius:6,fillColor:color,color:"#fff",weight:1.5,fillOpacity:.9}).addTo(vmapObj);
    mk.bindPopup(`<b>${esc(v.chain)}</b><br>${esc(v.addr)}<br>${esc(v.district)} · ${v.rating?"⭐ "+v.rating+" · ":""}${vBoxCount(v)} ${plural(vBoxCount(v),["бокс","бокса","боксов"])}<br><button data-action="open-venue" data-id="${esc(v.id)}" style="margin-top:6px;width:100%;background:oklch(22% .03 45);border:0;padding:7px;border-radius:999px;font-weight:700;color:oklch(97% .018 82);cursor:pointer">Смотреть боксы</button>`);
    return mk;
  });
  if(vs.length){const g=L.featureGroup(vmapObj._mk); try{vmapObj.fitBounds(g.getBounds().pad(0.1));}catch(e){}}
}
const CAT_EMO={sweet:"🍩",bakery:"🥐",mixed:"🧺",snack:"🥪"};
function venueWin(fromMin,durH){
  const from=new Date(Date.now()+fromMin*60000); from.setMinutes(from.getMinutes()<30?0:30,0,0);
  const to=new Date(from.getTime()+durH*3600000);
  return win(from.toISOString(),to.toISOString());
}
window.openVenue=id=>{
  const v=(ALL_VENUES||[]).find(x=>x.id===id); if(!v)return;
  const m=CHAIN_META[v.chain]||{ic:"☕"};
  showModal(`<div class="mc">
    <div style="display:flex;gap:.7rem;align-items:center">
      <div class="logo ${m.cls}" style="width:52px;height:52px;border-radius:13px;display:grid;place-items:center;font-size:1.6rem;color:#fff">${m.ic}</div>
      <div><h3 style="margin:0">${esc(v.chain)}</h3><div style="font-size:.8rem;color:var(--txt2)">${esc(v.addr)} · ${esc(v.district)}${v.rating?" · ⭐ "+v.rating:""}</div></div>
    </div>
    <a href="https://2gis.kz/astana/firm/${v.id}" target="_blank" rel="noopener" style="display:inline-block;margin:.6rem 0 .2rem;font-size:.78rem;font-weight:700">🗺 Открыть в 2ГИС →</a>
    <p style="font-size:.8rem;color:var(--txt2);margin:.5rem 0 .3rem">Доступно сегодня — можно забрать:</p>
    <div id="vBoxes">${v.boxes.map((b,i)=>`
      <div class="lrow">
        <div style="font-size:1.4rem">${CAT_EMO[b.cat]||"🧺"}</div>
        <div class="g"><b>${esc(b.title)}</b>
          <div style="font-size:.76rem;color:var(--txt2)">⏱ ${venueWin(b.from,b.dur)} · осталось ${b.qty}</div>
          <div style="font-size:.8rem;margin-top:.1rem"><b style="color:var(--brown)">${money(b.price)}</b> <s style="color:#A08D7D">${money(b.value)}</s> <span style="color:var(--green);font-weight:800">−${Math.round((1-b.price/b.value)*100)}%</span></div>
        </div>
        <button class="btn" style="width:auto;padding:.5rem .8rem;font-size:.82rem" data-action="book-venue" data-id="${esc(v.id)}" data-index="${i}">Забрать</button>
      </div>`).join("")}</div>
    <button class="btn sec" data-action="close" style="margin-top:.8rem">Закрыть</button>
  </div>`);
};
window.bookVenueBox=(id,i)=>{
  if(APP_CONFIG.production){toast("Локальные демо-брони отключены",true);return;}
  const v=(ALL_VENUES||[]).find(x=>x.id===id); if(!v)return; const b=v.boxes[i]; if(!b||b.qty<=0)return;
  const code="YM-"+Math.random().toString(16).slice(2,6).toUpperCase();
  b.qty--; saveCode(code);
  let qr="";
  try{ if(typeof qrcode==="function"){const q=qrcode(0,"M");q.addData(code);q.make();qr=`<div class="qr">${q.createSvgTag({cellSize:6,margin:2})}</div>`;} }catch(e){}
  showModal(`<div class="mc ok-wrap" style="padding-top:1.3rem">
    <div class="ok-ic">✅</div><h3>Бокс забронирован!</h3>
    <p style="color:var(--txt2);font-size:.86rem;margin:.2rem 0 0">${esc(v.chain)} · ${esc(v.addr)}</p>
    ${qr}<div class="code">${esc(code)}</div>
    <p style="font-size:.84rem;color:var(--txt2);margin:.5rem 0">Покажите код на кассе.<br>Забрать: <b style="color:var(--brown)">${venueWin(b.from,b.dur)}</b></p>
    <p style="font-size:.8rem;color:var(--green);font-weight:700">🌱 Вы спасли ~0.5 кг еды и ~1.3 кг CO₂</p>
    <a class="btn sec" style="display:block;text-decoration:none;margin:.3rem 0 .5rem" href="https://2gis.kz/astana/firm/${v.id}" target="_blank" rel="noopener">🗺 Маршрут в 2ГИС</a>
    <button class="btn" data-action="close-load-venues">Готово</button>
  </div>`);
};
/* отзывы (демо) */
window.showReviews=async(partnerId,name)=>{
  showModal(`<div class="mc"><h3>${esc(name)}</h3><p style="font-size:.82rem;color:var(--txt2)">Загружаем отзывы…</p></div>`);
  let real=[];
  try{real=await get(`/partners/${partnerId}/reviews`);}catch(e){}
  const body=real.length
    ? `<p style="font-size:.76rem;color:var(--txt2);margin:.15rem 0 .5rem">Отзывы покупателей — только по подтверждённым заказам</p>
       ${real.map(r=>`<div class="rev"><b>${esc(r.author_name)}</b> <span class="st">${"★".repeat(r.rating)}${"☆".repeat(5-r.rating)}</span><br>${esc(r.text)}</div>`).join("")}`
    : APP_CONFIG.production
      ? `<p class="empty">Подтверждённых отзывов пока нет.</p>`
      : `<p style="font-size:.76rem;color:var(--txt2);margin:.15rem 0 .5rem">Демо-примеры отзывов:</p>
         ${(REVIEWS[name]||[["Гость","Пока нет отзывов — будь первым!",5]]).map(([n,t,s])=>`<div class="rev"><b>${esc(n)}</b> <span class="st">${"★".repeat(s)}${"☆".repeat(5-s)}</span><br>${esc(t)}</div>`).join("")}`;
  showModal(`<div class="mc"><h3>${esc(name)}</h3>${body}
    <button class="btn sec" data-action="close" style="margin-top:.9rem">Закрыть</button></div>`);
};
async function openBox(id){
  let b;try{b=await get("/boxes/"+id);}catch(e){toast(e.message,true);return;}
  showModal(`<div class="mh" style="background-image:url(img/${imgFor(b)})"><button class="x" data-action="close">✕</button></div>
    <div class="mc">
      <div style="color:var(--txt2);font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.04em">${esc(b.category_ru)}</div>
      <h3>${esc(b.title||b.partner_name)}</h3>
      <div style="color:var(--txt2);font-size:.84rem">${esc(b.partner_name)} · ${esc(b.address)} · ⭐ ${b.rating}
        · <a href="${gisUrl(b.partner_name,b.address)}" target="_blank" rel="noopener" style="font-weight:700">🗺 Маршрут</a></div>
      <div class="row"><span>Цена</span><b>${money(b.price)} <s style="color:#A08D7D;font-weight:400">${money(b.value_est)}</s> <span style="color:var(--green);font-weight:800">−${b.discount}%</span></b></div>
      <div class="row"><span>Самовывоз</span><span>${win(b.pickup_from,b.pickup_to)}</span></div>
      <div class="row"><span>Осталось</span><span>${b.qty_left} из ${b.qty_total}</span></div>
      ${b.description?`<div class="inside"><b>Что обычно внутри:</b> ${esc(b.description)}</div>`:""}
      <div class="rules"><b>Сюрприз-бокс.</b> Точный состав может отличаться — это набор из свежих остатков дня. Забрать нужно в окне самовывоза, иначе заказ сгорает (предоплата не возвращается). Если заведение не выдаст — полный возврат.</div>
      <label>Ваше имя <input id="oName" placeholder="Имя" /></label>
      <label>Телефон <input id="oPhone" placeholder="+7 7XX XXX XX XX" /></label>
      <button class="btn" id="payBtn" style="margin-top:.8rem">Оплатить ${money(b.price)}</button>
      <div id="kaspiSlot"></div>
      <button class="btn sec" id="shareBtn" style="margin-top:.5rem">🔗 Поделиться боксом</button>
      <div class="demo-pay">💳 Демо-оплата. В продакшене — Kaspi Pay / Kaspi QR.</div>
    </div>`);
  const acc=account();  // зарегистрированному покупателю подставляем только display name
  if(acc&&acc.role==="buyer"&&acc.name)$("#oName").value=acc.name;
  if(KASPI_SERVICE_ID){ // включается автоматически, когда появится service_id мерчанта
    $("#kaspiSlot").innerHTML=`<a href="https://kaspi.kz/pay/${encodeURIComponent(KASPI_SERVICE_ID)}?amount=${b.price}"
      style="display:block;text-align:center;background:#F14635;color:#fff;font-weight:800;padding:.8rem 1rem;border-radius:13px;margin-top:.5rem;text-decoration:none">Оплатить через Kaspi</a>`;
  }
  $("#shareBtn").onclick=async()=>{
    const url=location.origin+location.pathname+"?box="+encodeURIComponent(b.id);
    const data={title:"Yummy — "+(b.title||b.partner_name),text:`${b.title||b.partner_name} за ${money(b.price)} (скидка −${b.discount}%) в ${b.partner_name}`,url};
    try{ if(navigator.share){await navigator.share(data);} else {await navigator.clipboard.writeText(url);toast("Ссылка скопирована 🔗");} }
    catch(e){ try{await navigator.clipboard.writeText(url);toast("Ссылка скопирована 🔗");}catch(_){toast(url);} }
  };
  if(APP_CONFIG.production&&!APP_CONFIG.payments_enabled){
    $("#payBtn").disabled=true;$("#payBtn").textContent="Онлайн-оплата подключается";
  }
  $("#payBtn").onclick=async()=>{
    if(APP_CONFIG.production&&!APP_CONFIG.payments_enabled)return;
    const name=$("#oName").value.trim(), phone=$("#oPhone").value.trim();
    if(!name||phone.length<5){toast("Укажите имя и телефон",true);return;}
    $("#payBtn").disabled=true;$("#payBtn").textContent="Оплата…";
    try{
      const orderPayload={box_id:b.id,user_name:name,user_phone:phone};
      if(APP_CONFIG.payment_mode==="stripe"){
        const checkout=await post("/checkout/sessions",orderPayload);
        location.assign(checkout.checkout_url);return;
      }
      const res=await post("/orders",orderPayload);
      saveCode(res.order.code);successScreen(res);
    }catch(e){toast(e.message,true);$("#payBtn").disabled=false;$("#payBtn").textContent="Оплатить "+money(b.price);}
  };
}
function successScreen(res){
  const o=res.order;
  showModal(`<div class="mc ok-wrap" style="padding-top:1.4rem">
    <div class="ok-ic">✅</div>
    <h3>Бокс забронирован!</h3>
    <p style="color:var(--txt2);font-size:.86rem;margin:.2rem 0 0">${esc(o.partner_name)} · ${esc(o.address)}</p>
    <div class="qr">${res.qr_svg}</div>
    <div class="code">${esc(o.code)}</div>
    <p style="font-size:.84rem;color:var(--txt2);margin:.5rem 0">Покажите код или QR на кассе.<br>Забрать: <b style="color:var(--brown)">${win(o.pickup_from,o.pickup_to)}</b></p>
    <p style="font-size:.8rem;color:var(--green);font-weight:700;margin:.3rem 0 .6rem">🌱 Вы спасли ~${ECO_KG} кг еды и предотвратили ~${ECO_CO2} кг CO₂</p>
    <a class="btn sec" style="display:block;text-decoration:none;margin-bottom:.5rem" href="${gisUrl(o.partner_name,o.address)}" target="_blank" rel="noopener">🗺 Маршрут в 2ГИС</a>
    <button class="btn sec" data-action="close">Готово</button>
  </div>`);
}
function myCodes(){try{return JSON.parse(localStorage.getItem("ym_codes")||"[]");}catch(e){return [];}}
function saveCode(c){const a=myCodes();if(!a.includes(c)){a.unshift(c);localStorage.setItem("ym_codes",JSON.stringify(a.slice(0,20)));}updateCart();}
function updateCart(){const n=myCodes().length;const el=$("#cartCnt");el.textContent=n;el.classList.toggle("hidden",!n);}
async function renderMyOrders(){
  updateCart();
  const el=$("#myorders"); const a=account();
  let orders=null;
  if(a&&a.server){ try{orders=await get("/me/orders");}catch(e){} }  // кросс-девайс история аккаунта
  if(!orders){
    const codes=myCodes();
    if(!codes.length){el.innerHTML="";return;}
    orders=(await Promise.all(codes.map(c=>get("/orders/"+c).catch(()=>null)))).filter(Boolean);
  }
  if(!orders.length){el.innerHTML="";return;}
  const done=orders.filter(o=>o.status==="issued");
  const eco=done.length?`<p style="margin:0 0 .6rem;font-size:.82rem;font-weight:700;color:var(--green)">🌱 Вы спасли ~${(done.length*ECO_KG).toFixed(1)} кг еды · ${(done.length*ECO_CO2).toFixed(1)} кг CO₂ · сэкономили ≈${money(Math.round(done.reduce((s,o)=>s+o.price,0)*1.5))}</p>`:"";
  const reviewed=reviewedIds();
  el.innerHTML=`<div class="cardp"><h3>Мои заказы</h3>${eco}${orders.map(o=>`<div class="lrow">
    <div style="font-size:1.3rem">${o.emoji}</div>
    <div class="g"><b>${esc(o.code)}</b> · ${esc(o.partner_name)}
      <div style="font-size:.76rem;color:var(--txt2)">${win(o.pickup_from,o.pickup_to)} · ${money(o.price)}</div>
      ${(a&&a.server&&o.status==="paid"&&Date.now()>=Date.parse(o.pickup_from))?`<button class="linkbtn" data-action="support-refund" data-id="${esc(o.id)}">Не выдали заказ? Открыть заявку</button>`:""}
      ${(a&&a.server&&o.status==="issued"&&!reviewed.includes(o.id))?`<button class="linkbtn" data-action="leave-review" data-order-id="${esc(o.id)}" data-partner-id="${esc(o.partner_id)}" data-name="${esc(o.partner_name)}">⭐ Оставить отзыв</button>`:""}
      <button class="linkbtn" data-action="show-code" data-code="${esc(o.code)}">Показать код и QR</button></div>
    <span class="tag t-${o.status}">${STATUS_RU[o.status]}</span></div>`).join("")}</div>`;
}
function reviewedIds(){try{return JSON.parse(localStorage.getItem("ym_reviewed")||"[]");}catch(e){return [];}}
function markReviewed(id){const r=reviewedIds();if(!r.includes(id)){r.push(id);localStorage.setItem("ym_reviewed",JSON.stringify(r));}}
window.leaveReviewForm=(orderId,partnerId,partnerName)=>{
  showModal(`<div class="mc">
    <h3>Отзыв о ${esc(partnerName)}</h3>
    <label>Оценка <select id="rvStars"><option value="5">★★★★★ Отлично</option><option value="4">★★★★☆ Хорошо</option>
      <option value="3">★★★☆☆ Нормально</option><option value="2">★★☆☆☆ Так себе</option><option value="1">★☆☆☆☆ Плохо</option></select></label>
    <label>Комментарий <textarea id="rvText" rows="3" placeholder="Что понравилось или нет?"></textarea></label>
    <span class="ferr" id="rv_err"></span>
    <button class="btn" id="rvSend" style="margin-top:.6rem">Отправить отзыв</button>
    <button class="btn sec" data-action="close" style="margin-top:.5rem">Отмена</button>
  </div>`);
  $("#rvSend").onclick=async()=>{
    const text=$("#rvText").value.trim();
    if(text.length<3){$("#rv_err").textContent="Напишите пару слов";return;}
    const btn=$("#rvSend"); btn.disabled=true; btn.textContent="Отправляем…";
    try{
      await post(`/partners/${partnerId}/reviews`,{order_id:orderId,rating:+$("#rvStars").value,text});
      markReviewed(orderId); closeModal(); toast("Спасибо за отзыв! ⭐"); renderMyOrders();
    }catch(e){
      if(/уже оставлен/i.test(e.message))markReviewed(orderId);
      $("#rv_err").textContent=e.message; btn.disabled=false; btn.textContent="Отправить отзыв";
    }
  };
};
window.showCode=code=>{
  // QR рисуем на месте, если библиотека есть (Pages-версия); иначе — крупный код
  let qr="";
  try{ if(typeof qrcode==="function"){const q=qrcode(0,"M");q.addData(code);q.make();qr=`<div class="qr">${q.createSvgTag({cellSize:6,margin:2})}</div>`;} }catch(e){}
  showModal(`<div class="mc ok-wrap" style="padding-top:1.3rem">
    <h3>Код выдачи</h3>${qr}
    <div class="code">${esc(code)}</div>
    <p style="font-size:.84rem;color:var(--txt2);margin:.5rem 0">Покажите ${qr?"QR или ":""}код на кассе заведения.</p>
    <button class="btn sec" data-action="close">Закрыть</button></div>`);
};
window.refundRequestForm=orderId=>{
  showModal(`<div class="mc"><h3>Запрос на возврат</h3><label>Причина <select id="rrReason"><option value="not_issued">Заказ не выдали</option><option value="venue_closed">Заведение закрыто</option><option value="other">Другое</option></select></label><label>Подробности <textarea id="rrDetails" rows="3" maxlength="1000"></textarea><span class="ferr" id="rrErr"></span></label><button class="btn" id="rrSend">Отправить</button><button class="btn sec" data-action="close">Отмена</button></div>`);
  $("#rrSend").onclick=async()=>{const details=$("#rrDetails").value.trim();if(details.length<5){$("#rrErr").textContent="Опишите ситуацию";return;}
    try{await post(`/me/orders/${orderId}/refund-requests`,{reason:$("#rrReason").value,details});closeModal();toast("Заявка принята поддержкой");renderMyOrders();}catch(e){$("#rrErr").textContent=e.message;}};
};

/* Возврат не автоматический: решение принимает MFA-admin с audit trail. */

/* ============ ПАРТНЁР ============ */
let CURRENT_PARTNER=null;
async function loadPartner(){
  try{
    const me=await get("/session/me");
    CURRENT_PARTNER=await get("/partner/me");
    if(me.partner_status!=="approved"){
      $("#pIdentity").innerHTML=`<b>${esc(CURRENT_PARTNER.name)}</b><div style="font-size:.8rem;color:var(--txt2);margin-top:.35rem">⏳ Статус заявки: <b>${esc(me.partner_status||"pending")}</b>. Публикация и выдача откроются после проверки администратором.</div>`;
      CURRENT_PARTNER=null;return;
    }
    $("#pIdentity").innerHTML=`<b>${esc(CURRENT_PARTNER.name)}</b><div style="font-size:.8rem;color:var(--txt2);margin-top:.2rem">📍 ${esc(CURRENT_PARTNER.address)} · ${esc(CURRENT_PARTNER.district)}</div>`;
    await loadPartnerData();
  }catch(e){
    CURRENT_PARTNER=null;
    $("#pIdentity").textContent=e.message;
    toast(e.message,true);
  }
}
async function loadPartnerData(){
  if(!CURRENT_PARTNER)return;
  let boxes=[],orders=[];
  try{boxes=await get("/partner/me/boxes");}catch(e){toast(e.message,true);}
  try{orders=await get("/partner/me/orders");}catch(e){toast(e.message,true);}
  // мини-аналитика точки (семя CRM-тарифа): выручка, продажи, выкуп, остаток
  const done=orders.filter(o=>o.status==="issued"), act=orders.filter(o=>o.status==="paid");
  const noshow=orders.filter(o=>o.status==="expired").length;
  const revenue=done.concat(act).reduce((s,o)=>s+o.price,0);
  const closedTotal=done.length+noshow;
  const fill=closedTotal?Math.round(done.length/closedTotal*100):null;
  const leftNow=boxes.reduce((s,b)=>s+b.qty_left,0);
  $("#pStats").innerHTML=[
    [money(revenue),"выручка с боксов"],[done.length+act.length,plural(done.length+act.length,["продажа","продажи","продаж"])],
    [fill===null?"—":fill+"%","выкуп (забрали)"],[leftNow,plural(leftNow,["бокс","бокса","боксов"])+" в продаже"],
  ].map(([v,l])=>`<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("");
  $("#pBoxes").innerHTML=boxes.length?boxes.map(b=>`<div class="lrow"><div style="font-size:1.2rem">${b.emoji}</div>
    <div class="g"><b>${esc(b.title||b.category_ru)}</b><div style="font-size:.76rem;color:var(--txt2)">${money(b.price)} · ${win(b.pickup_from,b.pickup_to)}</div></div>
    <span class="tag ${b.qty_left>0?"t-issued":"t-expired"}">${b.qty_left}/${b.qty_total}</span></div>`).join(""):'<p class="empty">Боксов пока нет.</p>';
  $("#pOrders").innerHTML=orders.length?orders.map(o=>orderRow(o)).join(""):'<p class="empty">Броней пока нет.</p>';
}
function orderRow(o,admin=false){
  return `<div class="lrow"><div style="font-size:1.2rem">${o.emoji}</div>
    <div class="g"><b>${esc(o.code)}</b> · ${esc(o.user_name)} <span style="color:var(--txt2)">${esc(o.user_phone)}</span>
      <div style="font-size:.76rem;color:var(--txt2)">${admin?esc(o.partner_name)+" · ":""}${money(o.price)} · ${win(o.pickup_from,o.pickup_to)}</div></div>
    <span class="tag t-${o.status}">${STATUS_RU[o.status]}</span>
    ${admin&&(o.status==="paid")?`<button class="btn sec" style="width:auto;padding:.3rem .6rem;font-size:.74rem" data-action="refund" data-id="${esc(o.id)}">Возврат</button>`:""}</div>`;
}
$("#boxForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const hours=Math.max(1,+$("#bHours").value||4);
  const now=new Date(), to=new Date(now.getTime()+hours*3600*1000);
  if(!CURRENT_PARTNER){toast("Профиль заведения не загружен",true);return;}
  const body={partner_id:CURRENT_PARTNER.id,category:$("#bCat").value,title:$("#bTitle").value.trim(),
    price:+$("#bPrice").value,value_est:+$("#bValue").value,qty:+$("#bQty").value,
    pickup_from:now.toISOString(),pickup_to:to.toISOString(),description:$("#bDesc").value.trim()};
  if(!(body.price>=100&&body.price<=50000)){toast("Цена бокса — от 100 до 50 000 ₸",true);return;}
  if(body.value_est<body.price){toast("Ценность внутри должна быть не ниже цены",true);return;}
  if(!(body.qty>=1&&body.qty<=50)){toast("Количество — от 1 до 50",true);return;}
  try{await post("/boxes",body);toast("Бокс опубликован ✓");e.target.reset();$("#bPrice").value=990;$("#bValue").value=2600;$("#bQty").value=5;$("#bHours").value=4;loadPartnerData();}
  catch(err){toast(err.message,true);}
});
$("#bAiBtn").onclick=async()=>{
  const notes=$("#bDesc").value.trim();
  if(notes.length<2){toast("Сначала напиши черновик — хотя бы пару слов",true);return;}
  const btn=$("#bAiBtn"), old=btn.textContent; btn.disabled=true; btn.textContent="Генерирую…";
  try{
    const r=await post("/ai/describe-box",{category:$("#bCat").value,notes});
    $("#bDesc").value=r.description;
    toast(r.ai?"Описание улучшено ИИ ✨":"Описание собрано по шаблону (демо-режим без AI-ключа)");
  }catch(e){toast(e.message,true);}
  btn.disabled=false; btn.textContent=old;
};
$("#redeemCode").addEventListener("input",e=>{e.target.value=e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g,"");});
$("#redeemBtn").onclick=async()=>{
  const code=$("#redeemCode").value.trim();if(!code){toast("Введите код",true);return;}
  try{const r=await post("/redeem",{code});
    $("#redeemRes").innerHTML=`<span class="tag ${r.ok?"t-issued":"t-expired"}">${r.ok?"✓ ":"✕ "}${esc(r.message)}</span>`+
      (r.order?` <span style="color:var(--txt2)">${esc(r.order.partner_name)} · ${money(r.order.price)}</span>`:"");
    if(r.ok){toast("Выдано ✓");loadPartnerData();}
  }catch(e){toast(e.message,true);}
};
/* QR-сканер без runtime CDN: нативный BarcodeDetector + ручной код как fallback. */
let _scanner=null;
function stopScanner(){
  if(_scanner){clearTimeout(_scanner.timer);_scanner.stream.getTracks().forEach(t=>t.stop());_scanner=null;}
  const box=$("#scanBox");box.classList.add("hidden");box.innerHTML="";
  $("#scanBtn").textContent="📷 Сканировать QR камерой";
}
$("#scanBtn").onclick=async()=>{
  if(_scanner){stopScanner();return;}
  if(!("BarcodeDetector" in window)||!navigator.mediaDevices?.getUserMedia){
    toast("Этот браузер не поддерживает безопасный QR-сканер — введите код вручную",true);return;
  }
  const box=$("#scanBox");box.classList.remove("hidden");
  box.innerHTML='<video id="qrVideo" autoplay playsinline muted style="width:100%;display:block"></video>';
  $("#scanBtn").textContent="✕ Остановить сканер";
  try{
    const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"},audio:false});
    const video=$("#qrVideo");video.srcObject=stream;
    const detector=new BarcodeDetector({formats:["qr_code"]});
    _scanner={stream,timer:null};
    const detect=async()=>{
      if(!_scanner)return;
      try{
        const found=await detector.detect(video), code=(found[0]?.rawValue||"").trim().toUpperCase();
        if(/^YM-/.test(code)){stopScanner();$("#redeemCode").value=code;$("#redeemBtn").click();return;}
      }catch(e){}
      if(_scanner)_scanner.timer=setTimeout(detect,250);
    };
    _scanner.timer=setTimeout(detect,250);
  }catch(e){stopScanner();toast("Нет доступа к камере",true);}
};

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
$("#inviteCreate").onclick=async()=>{
  const email=$("#inviteEmail").value.trim(),role=$("#inviteRole").value;
  const body={email,partner_role:role,partner_id:$("#invitePartner").value.trim()||null,brand_name:$("#inviteBrand").value.trim(),address:$("#inviteAddress").value.trim(),district:$("#inviteDistrict").value.trim()};
  try{const result=await post("/admin/staff-invitations",body);$("#inviteResult").innerHTML=`<p>Ссылка действует 7 дней:</p><input id="inviteLink" readonly value="${esc(result.invite_url)}" /><button class="btn sec" id="copyInvite">Копировать</button>`;$("#copyInvite").onclick=()=>navigator.clipboard.writeText(result.invite_url).then(()=>toast("Ссылка скопирована"));}catch(e){toast(e.message,true);}
};

async function loadAdmin(){
  let s={},orders=[],partners=[],refunds=[];
  try{s=await get("/admin/stats");}catch(e){}
  try{orders=await get("/admin/orders");}catch(e){}
  try{partners=await get("/admin/partner-applications");}catch(e){}
  try{refunds=await get("/admin/refund-requests");}catch(e){}
  $("#aStats").innerHTML=[
    [money(s.gmv||0),"GMV (оборот)"],[s.orders_total||0,"заказов"],
    [(s.fill_rate||0)+"%","выкуплено (fill rate)"],[s.no_show||0,"не забрали (no-show)"],
    [s.issued||0,"выдано"],[s.active||0,"активных"],[s.refunds||0,"возвратов"],[(s.gmv? Math.round(s.gmv*0.1):0)+" ₸","take 10% (прогноз)"],
  ].map(([v,l])=>`<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("");
  $("#aPartners").innerHTML=partners.length?partners.map(p=>{
    const verify=!p.email_verified?`<button class="btn sec" data-action="verify-email" data-id="${esc(p.user_id)}">Email ✓ вручную</button>`:"";
    const actions=verify+(p.status==="pending"
      ?`<button class="btn sec" data-action="partner-status" data-id="${esc(p.user_id)}" data-status="approved">Одобрить</button><button class="btn sec" data-action="partner-status" data-id="${esc(p.user_id)}" data-status="rejected">Отклонить</button>`
      :p.status==="approved"
        ?`<button class="btn sec" data-action="partner-status" data-id="${esc(p.user_id)}" data-status="suspended">Приостановить</button>`
        :`<button class="btn sec" data-action="partner-status" data-id="${esc(p.user_id)}" data-status="approved">Одобрить снова</button>`);
    return `<div class="lrow"><div class="g"><b>${esc(p.brand_name)}</b><div style="font-size:.76rem;color:var(--txt2)">${esc(p.email)} · ${esc(p.address)} · ${esc(p.district)}</div></div><span class="tag">${esc(p.status)}</span><div style="display:flex;gap:.3rem">${actions}</div></div>`;
  }).join(""):'<p class="empty">Заявок пока нет.</p>';
  $("#aRefunds").innerHTML=refunds.length?refunds.map(r=>{
    const actions=r.status==="pending"||r.status==="reviewing"
      ?`<button class="btn sec" data-action="refund-decision" data-id="${esc(r.id)}" data-action-value="reviewing">В работу</button><button class="btn sec" data-action="refund-decision" data-id="${esc(r.id)}" data-action-value="approve">Одобрить</button><button class="btn sec" data-action="refund-decision" data-id="${esc(r.id)}" data-action-value="reject">Отклонить</button>`:"";
    return `<div class="lrow"><div class="g"><b>${esc(r.reason)}</b><div style="font-size:.76rem;color:var(--txt2)">${esc(r.details)} · order ${esc(r.order_id)}</div></div><span class="tag">${esc(r.status)}</span><div style="display:flex;gap:.3rem">${actions}</div></div>`;
  }).join(""):'<p class="empty">Запросов пока нет.</p>';
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
}
window.refund=async id=>{try{await post("/admin/refund/"+id);toast("Возврат оформлен");loadAdmin();}catch(e){toast(e.message,true);}};
window.decideRefund=async(id,action)=>{
  const resolution=prompt(`Решение по заявке (${action}):`)||"";if(resolution.length<3)return;
  try{await post(`/admin/refund-requests/${id}/decision`,{action,resolution});toast("Решение сохранено");loadAdmin();}
  catch(e){toast(e.message,true);}
};
window.verifyEmailManually=async id=>{
  const reason=prompt("Как email был подтверждён вручную?")||"";if(reason.length<3)return;
  try{await post(`/admin/users/${id}/verify-email`,{reason});toast("Email подтверждён");loadAdmin();}
  catch(e){toast(e.message,true);}
};
window.setPartnerStatus=async(id,status)=>{
  const reason=prompt(`Причина изменения статуса на ${status}:`)||"";
  try{await post(`/admin/partners/${id}/status`,{status,reason});toast(`Статус партнёра: ${status}`);loadAdmin();}
  catch(e){toast(e.message,true);}
};

/* ---- документы (демо-версии) ---- */
const LEGAL={
 offer:["Публичная оферта",`<p style="color:var(--txt2);font-size:.8rem"><i>Рабочая редакция. Перед публичным применением проверяется юристом РК. Полный текст — в репозитории (/legal/oferta.md).</i></p>
  <p><b>1. Предмет.</b> Yummy — платформа-агент: соединяет заведения-партнёры и покупателей для продажи сюрприз-боксов из свежих непроданных за день товаров. Продавцом и ответственным за качество является Партнёр.</p>
  <p><b>2. Заказ и оплата.</b> Покупатель оплачивает бокс онлайн и получает код/QR. Оплата — предоплата брони; средства перечисляются Партнёру за вычетом вознаграждения Сервиса после выдачи.</p>
  <p><b>3. Выдача.</b> По коду/QR в окне самовывоза. Состав бокса — сюрприз; претензии «попался не тот набор» не принимаются, если товар свежий и соответствует категории.</p>
  <p><b>4. Возвраты.</b> Не забрал в окне — бронь сгорает, предоплата не возвращается (товар был зарезервирован). Партнёр не выдал — полный возврат. Претензия к качеству — рассмотрение до 3 рабочих дней, при подтверждении возврат.</p>
  <p><b>5. Ответственность и права.</b> За безопасность еды отвечает Партнёр по законам РК. О пищевой аллергии сообщать Партнёру до получения. Оферта не ограничивает права по Закону РК «О защите прав потребителей».</p>`],
 privacy:["Политика конфиденциальности",`<p style="color:var(--txt2);font-size:.8rem"><i>Составлена с опорой на Закон РК «О персональных данных» № 94-V. Рабочая редакция, /legal/privacy.md.</i></p>
  <p><b>1. Данные.</b> Email, хеш пароля, имя, телефон, история заказов, аудит-лог (IP/время) — для входа, выдачи, возвратов и безопасности. Данные банковских карт и CVV НЕ собираем и НЕ храним — оплата на стороне провайдера.</p>
  <p><b>2. Согласие.</b> При регистрации даётся явное согласие на обработку (ст. 8 № 94-V). Отзыв = удаление аккаунта.</p>
  <p><b>3. Передача.</b> Заведению — имя и телефон только по оплаченному заказу. Провайдеру — сумма платежа. Третьим лицам не передаём и не продаём.</p>
  <p><b>4. Защита.</b> Пароли — только memory-hard хеш Argon2id с уникальной солью. Browser-сессия — HttpOnly cookies + CSRF; access/refresh недоступны JavaScript.</p>
  <p><b>5. Ваши права (реализованы в приложении).</b> Скачать свои данные · удалить аккаунт (обезличивание PII) · выйти со всех устройств · отозвать согласие.</p>`],
 quality:["Стандарты пищевой безопасности",`<p style="color:var(--txt2);font-size:.8rem"><i>Согласуются с санитарными требованиями РК (ТР ТС 021/2011, СанПиН). /legal/food-safety.md.</i></p>
  <p><b>Что продаётся:</b> только свежий товар текущего дня в допустимом окне реализации. Просрочка, вчерашний, повторно размороженный — запрещены.</p>
  <p><b>Хранение и выдача:</b> температурный режим; чистая пищевая упаковка; самовывоз строго день в день; окно самовывоза — в пределах пригодности товара.</p>
  <p><b>Аллергены:</b> состав заранее не публикуется, поэтому по запросу покупателя персонал обязан устно сообщить о наличии основных аллергенов (орехи, глютен, молоко, яйцо).</p>
  <p><b>Ответственность:</b> за качество отвечает заведение по законам РК. Жалоба → проверка → возврат; при повторных нарушениях — отключение партнёра.</p>`],
 agreement:["Договор с заведением",`<p style="color:var(--txt2);font-size:.8rem"><i>Агентский договор-оферта. Рабочая редакция, /legal/partner-agreement.md.</i></p>
  <p><b>Модель.</b> Yummy — агент: платформа + приём оплаты от имени заведения. Заведение — продавец.</p>
  <p><b>Вознаграждение и выплаты.</b> Комиссия сервиса __% с выданного заказа (на пилоте — 0%). Выплаты заведению — раз в неделю (по средам) за вычетом комиссии.</p>
  <p><b>Обязанности заведения.</b> Свежий товар дня, санитарные нормы РК, выдача по коду/QR в окне, достоверная категория/состав, обученный персонал.</p>
  <p><b>Обязанности сервиса.</b> Работа платформы, приём оплаты, своевременные выплаты, отчёт по заказам, неразглашение данных.</p>
  <p><b>Споры.</b> Обоснованная жалоба → возврат + объяснение партнёра. Систематические нарушения → приостановка/прекращение. Расторжение — с уведомлением за 7 дней.</p>`],
};
window.showLegal=k=>{const [t,body]=LEGAL[k];
  showModal(`<div class="mc"><h3>${t}</h3><div class="legal-txt">${body}</div>
  <button class="btn sec" data-action="close" style="margin-top:.9rem">Закрыть</button></div>`);};

/* ---- модалка ---- */
function showModal(html){const m=$("#modal");m.className="modal-bg";
  m.innerHTML=`<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  m.onclick=e=>{if(e.target===m)closeModal();};
  const inp=m.querySelector("input,button");if(inp)inp.focus();}
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("#modal").classList.contains("hidden"))closeModal();});
window.closeModal=()=>{$("#modal").className="hidden";$("#modal").innerHTML="";if(!$("#view-store").classList.contains("hidden"))renderMyOrders();};

/* ---- уведомление о хранении данных ---- */
$("#yr").textContent=new Date().getFullYear();
if(!localStorage.getItem("ym_cookies")){
  const cb=document.createElement("div"),demo=typeof API_BASE!=="undefined"&&API_BASE==="";cb.className="cookiebar";
  const msg=demo
    ?"Изолированная демка: коды заказов, избранное и фильтры хранятся только в этом браузере."
    :"Сессия входа хранится в защищённых HttpOnly cookies; коды заказов, избранное и фильтры — локально в браузере.";
  cb.innerHTML=`<span>${msg}</span><button>Понятно</button>`;
  cb.querySelector("button").onclick=()=>{localStorage.setItem("ym_cookies","1");cb.remove();};
  document.body.appendChild(cb);
}

/* PWA: установка на телефон + оффлайн-доступ к купленным кодам */
if("serviceWorker" in navigator){navigator.serviceWorker.register("sw.js").catch(()=>{});}

/* Кнопка «Установить приложение» (паттерн из Google WebFundamentals):
   перехватываем системный баннер и показываем свою кнопку в футере */
let _bip=null;
window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();_bip=e;$("#installBtn").classList.remove("hidden");});
window.addEventListener("appinstalled",()=>{$("#installBtn").classList.add("hidden");toast("Yummy установлен 📲");});
$("#installBtn").onclick=async()=>{if(!_bip)return;_bip.prompt();try{await _bip.userChoice;}catch(e){} _bip=null;$("#installBtn").classList.add("hidden");};

/* Живые дашборды (реактивность в духе marimo): админка/партнёрка сами
   подтягивают свежие заказы, без F5 — только когда вкладка видима */
setInterval(()=>{
  if(document.hidden)return;
  if(window.__view==="admin")loadAdmin();
  else if(window.__view==="partner"&&CURRENT_PARTNER)loadPartnerData();
},15000);

/* Pull-to-refresh на мобиле (паттерн vux/WeUI) */
let _ptrY=0,_ptrOn=false;
document.addEventListener("touchstart",e=>{
  if(window.scrollY===0&&(window.__view==="store"||window.__view==="venues")){_ptrY=e.touches[0].clientY;_ptrOn=true;}
},{passive:true});
document.addEventListener("touchmove",e=>{
  if(!_ptrOn)return;
  const d=e.touches[0].clientY-_ptrY, el=$("#ptr");
  if(d>25&&window.scrollY===0){el.classList.remove("hidden");el.style.top=Math.min(d-25,70)+"px";el.style.transform=`translateX(-50%) rotate(${d*2}deg)`;}
},{passive:true});
document.addEventListener("touchend",()=>{
  if(!_ptrOn)return;_ptrOn=false;
  const el=$("#ptr"), d=parseInt(el.style.top)||0;
  el.classList.add("hidden");el.style.top="-60px";
  if(d>=60){toast("Обновляем…");window.__view==="venues"?loadVenues():loadStore();}
});

async function restoreBrowserSession(){
  const a=account();if(!a?.server)return;
  let user=null;
  try{user=await get("/session/me");}
  catch(e){try{await post("/session/refresh");user=await get("/session/me");}catch(_){setAccount(null);sessionStorage.removeItem("ym_staff");}}
  if(user){const roles={customer:"buyer",partner:"partner",admin:"admin"};setAccount({role:roles[user.role]||"buyer",name:user.brand_name||a.name,server:true,emailVerified:!!user.email_verified});
    if(user.role==="partner"||user.role==="admin")sessionStorage.setItem("ym_staff","1");}
}

function invitationForm(token){
  showModal(`<div class="mc"><h3>Приглашение в команду Yummy</h3><p>Создайте персональный аккаунт сотрудника. Ссылка одноразовая.</p><label>Пароль <input id="invitePass" type="password" autocomplete="new-password" /><span class="ferr" id="inviteErr"></span></label><label class="consent"><input type="checkbox" id="inviteTerms" /> Принимаю документы сервиса</label><button class="btn" id="inviteAccept">Принять приглашение</button></div>`);
  $("#inviteAccept").onclick=async()=>{const password=$("#invitePass").value,err=_pwErr(password);if(err){$("#inviteErr").textContent=err;return;}if(!$("#inviteTerms").checked){$("#inviteErr").textContent="Нужно принять документы";return;}
    try{const result=await post("/session/invitations/accept",{token,password,accepted_terms:true}),u=result.user;setAccount({role:"partner",name:u.brand_name||"Сотрудник",server:true,emailVerified:true});closeModal();toast("Доступ к заведению открыт");switchView("partner");}catch(e){$("#inviteErr").textContent=e.message;}};
}

async function confirmStripePayment(sessionId){
  showModal('<div class="mc"><h3>Проверяем оплату…</h3><p>Ожидаем подтверждённый Stripe webhook.</p></div>');
  for(let attempt=0;attempt<12;attempt++){
    try{const status=await get(`/checkout/sessions/${encodeURIComponent(sessionId)}`);
      if(status.payment_status==="paid"&&status.order){saveCode(status.order.code);successScreen({order:status.order,qr_svg:status.qr_svg});return;}
      if(["failed","expired"].includes(status.payment_status)){closeModal();toast("Оплата не завершена",true);return;}
    }catch(e){}
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
  closeModal();toast("Платёж обрабатывается — проверьте заказы позже",true);
}

async function bootstrap(){
  await restoreBrowserSession();
  try{APP_CONFIG=await get("/config");}catch(e){}
  applyEnvironmentVisibility();
  renderAccount();window.__view="store";
  if(!account())switchView("landing");
  await loadStore();
  const qs=new URLSearchParams(location.search),verify=qs.get("verify"),reset=qs.get("reset"),invite=qs.get("invite");
  if(verify){try{await post("/auth/email/verify/confirm",{token:verify});toast("Email подтверждён ✓");const a=account();if(a){a.emailVerified=true;setAccount(a);}}catch(e){toast(e.message,true);}history.replaceState({},"",location.pathname);}
  if(reset){resetPasswordForm(reset);history.replaceState({},"",location.pathname);return;}
  if(invite){invitationForm(invite);history.replaceState({},"",location.pathname);return;}
  if(qs.get("payment")==="success"&&qs.get("session_id")){await confirmStripePayment(qs.get("session_id"));history.replaceState({},"",location.pathname);return;}
  if(qs.get("payment")==="cancelled")toast("Оплата отменена — резерв освободится автоматически",true);
  const bid=qs.get("box");if(bid)openBox(bid);
  const nav=qs.get("nav");if(nav==="venues")switchView("venues");else if(nav==="orders")gotoOrders();
}
bootstrap();
