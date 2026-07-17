import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const checkoutCreated = new Counter('checkout_created');
const BASE_URL = __ENV.BASE_URL;
const BOX_ID = __ENV.BOX_ID;
const TOKEN = __ENV.BEARER_TOKEN;
if (!BASE_URL || !BOX_ID) throw new Error('BASE_URL and BOX_ID required');

export const options = {
  scenarios: { race: { executor: 'per-vu-iterations', vus: 25, iterations: 1, maxDuration: '20s' } },
  thresholds: { checks: ['rate>0.99'], http_req_duration: ['p(95)<2000'], checkout_created: ['count==1'] },
};

export default function () {
  const headers = { 'Content-Type': 'application/json' };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const response = http.post(`${BASE_URL}/checkout/sessions`, JSON.stringify({
    box_id: BOX_ID, user_name: `race-${__VU}`, user_phone: '+77000000000',
  }), { headers, tags: { endpoint: 'checkout-race' } });
  if (response.status === 201) checkoutCreated.add(1);
  check(response, { 'only expected status': r => [201, 409, 503].includes(r.status) });
}

export function handleSummary(data) {
  return { stdout: JSON.stringify({
    requests: data.metrics.http_reqs.values.count,
    failures: data.metrics.http_req_failed.values.rate,
  }, null, 2) };
}
