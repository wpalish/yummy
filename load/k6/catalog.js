import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8021';
export const options = {
  scenarios: {
    catalog: { executor: 'ramping-arrival-rate', startRate: 5, timeUnit: '1s',
      preAllocatedVUs: 20, maxVUs: 100,
      stages: [{ target: 20, duration: '30s' }, { target: 50, duration: '60s' },
               { target: 0, duration: '15s' }] },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{endpoint:catalog}': ['p(95)<500', 'p(99)<1000'],
  },
};

export default function () {
  const boxes = http.get(`${BASE_URL}/boxes`, { tags: { endpoint: 'catalog' } });
  check(boxes, { 'catalog 200': r => r.status === 200, 'catalog json': r => Array.isArray(r.json()) });
  const districts = http.get(`${BASE_URL}/districts`, { tags: { endpoint: 'catalog' } });
  check(districts, { 'districts 200': r => r.status === 200 });
  sleep(Math.random() * 0.5);
}
