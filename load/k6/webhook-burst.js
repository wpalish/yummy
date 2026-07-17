import http from 'k6/http';
import crypto from 'k6/crypto';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL;
const SECRET = __ENV.STRIPE_WEBHOOK_SECRET;
const EVENT_JSON = __ENV.EVENT_JSON;
if (!BASE_URL || !SECRET || !EVENT_JSON) throw new Error('BASE_URL, STRIPE_WEBHOOK_SECRET and EVENT_JSON required');

export const options = {
  scenarios: { burst: { executor: 'shared-iterations', vus: 50, iterations: 200, maxDuration: '30s' } },
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(99)<2000'] },
};

export default function () {
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = crypto.hmac('sha256', SECRET, `${timestamp}.${EVENT_JSON}`, 'hex');
  const response = http.post(`${BASE_URL}/webhooks/stripe`, EVENT_JSON, {
    headers: { 'Content-Type': 'application/json', 'Stripe-Signature': `t=${timestamp},v1=${signature}` },
    tags: { endpoint: 'stripe-webhook' },
  });
  check(response, { 'webhook accepted/idempotent': r => r.status === 200 });
}
