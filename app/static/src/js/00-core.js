const $=s=>document.querySelector(s);

/* ===== Делегирование кликов вместо inline onclick (CSP: без unsafe-inline) =====
   Каждый интерактивный элемент несёт data-act + при нужде data-a1..a3.
   Аргументы читаются как строки из dataset — это XSS-безопасно (в отличие от
   подстановки в JS-строку внутри onclick). Обработчики резолвятся по клику,
   поэтому порядок объявления функций ниже не важен. */
const ACT = {
  closeModal:      () => closeModal(),
  gotoOrders:      () => gotoOrders(),
  openLogin:       () => openLogin(),
  scrollToBoxes:   () => scrollToBoxes(),
  changePwForm:    () => changePwForm(),
  logoutAll:       () => logoutAll(),
  exportMe:        () => exportMe(),
  deleteMeConfirm: () => deleteMeConfirm(),
  logout:          () => logout(),
  onbBuyer:        () => onbBuyer(),
  onbPartner:      () => onbPartner(),
  partnerInfo:     () => { $("#onboard").className="onb"; onbPartner(); },
  onbGuest:        () => onbGuest(),
  loginForm:       () => loginForm(),
  forgotPw:        () => forgotPwForm(),
  showOnboarding:  () => showOnboarding(),
  viewVenues:      () => switchView("venues"),
  guestStore:      () => { onbGuest(); switchView("store"); },
  guestVenues:     () => { onbGuest(); switchView("venues"); },
  closeGotoOrders: () => { closeModal(); gotoOrders(); },
  closeShowOnb:    () => { closeModal(); showOnboarding(); },
  closeLoadVenues: () => { closeModal(); loadVenues(); },
  showLegal:       el => showLegal(el.dataset.a1),
  landRole:        el => landRole(el.dataset.a1),
  landRoleScroll:  el => { landRole(el.dataset.a1); document.querySelector(el.dataset.a2).scrollIntoView({behavior:"smooth"}); },
  scrollTo:        el => document.querySelector(el.dataset.a1).scrollIntoView({behavior:"smooth"}),
  soon:            el => toast(el.dataset.a1),
  toggleFav:       el => toggleFav(el.dataset.a1),
  showReviews:     el => showReviews(el.dataset.pid, el.dataset.name),
  openVenue:       el => openVenue(el.dataset.a1),
  callVenue:       el => callVenue(el.dataset.a1),
  editBox:         el => editBoxForm(el.dataset.a1),
  closeBox:        el => closeBoxConfirm(el.dataset.a1, el.dataset.a2),
  blockUser:       el => toggleUserBlock(el.dataset.a1, el.dataset.a2==="1"),
  revokeUser:      el => revokeUserSessions(el.dataset.a1),
  staffRole:       el => staffSetRole(el.dataset.a1, el.dataset.a2),
  staffActive:     el => staffSetActive(el.dataset.a1, el.dataset.a2==="1"),
  suspendPay:      el => suspendPay(el.dataset.a1),
  totpOn:          () => totpOn(),
  totpOff:         () => totpOff(),
  rotatePay:       el => rotatePay(el.dataset.a1),
  makeInvoice:     el => makeInvoice(el.dataset.a1),
  invoicePaid:     el => invoicePaid(el.dataset.a1),
  invoiceVoid:     el => invoiceVoid(el.dataset.a1),
  csvAll:          () => downloadCsv("/admin/orders.csv","yummy-orders.csv"),
  csvPartner:      el => downloadCsv(`/partners/${el.dataset.a1}/orders.csv`,"yummy-orders.csv"),
  mapShop:         el => shopFromMap(el.dataset.name),
  cancelOrder:     el => cancelOrder(el.dataset.a1),
  userRefund:      el => userRefund(el.dataset.a1),
  showCode:        el => showCode(el.dataset.a1),
  leaveReviewForm: el => leaveReviewForm(el.dataset.a1, el.dataset.a2, el.dataset.a3),
  refund:          el => refund(el.dataset.a1),
  publishTpl:      el => publishTpl(el.dataset.a1),
  delTpl:          el => delTpl(el.dataset.a1),
  connectPay:      el => connectPay(el.dataset.a1),
  activatePay:     el => activatePay(el.dataset.a1),
  setRate:         el => setRate(el.dataset.a1),
};
document.addEventListener("click", ev => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const fn = ACT[el.dataset.act];
  if (!fn) return;
  if (el.dataset.stop) ev.stopPropagation();
  fn(el, ev);
});

