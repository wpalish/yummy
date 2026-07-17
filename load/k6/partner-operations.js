import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL;
const TOKEN = __ENV.PARTNER_BEARER_TOKEN;
const PICKUP_CODE = __ENV.PICKUP_CODE;
if (!BASE_URL || !TOKEN) throw new Error('BASE_URL and PARTNER_BEARER_TOKEN required');
const issued = new Counter('redeem_success');

export const options = {
  scenarios: {
    orders: { executor: 'constant-vus', vus: 20, duration: '60s', exec: 'orders' },
    redeemRace: { executor: 'per-vu-iterations', vus: PICKUP_CODE ? 20 : 0,
      iterations: 1, exec: 'redeem', startTime: '5s' },
  },
  thresholds: {
    'http_req_duration{endpoint:partner-orders}': ['p(95)<750'],
    redeem_success: ['count<=1'],
  },
};
const headers = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' };

export function orders() {
  const r = http.get(`${BASE_URL}/partner/me/orders`, { headers, tags: { endpoint: 'partner-orders' } });
  check(r, { 'orders 200': x => x.status === 200 }); sleep(0.25);
}
export function redeem() {
  if (!PICKUP_CODE) return;
  const r = http.post(`${BASE_URL}/redeem`, JSON.stringify({ code: PICKUP_CODE }),
                      { headers, tags: { endpoint: 'redeem' } });
  if (r.status === 200 && r.json('ok') === true) issued.add(1);
  check(r, { 'redeem controlled': x => x.status === 200 });
}
