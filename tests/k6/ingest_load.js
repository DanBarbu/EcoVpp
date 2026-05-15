/**
 * ECO-VPP Sprint 5 load test: 1,000 ingest req/s sustained.
 *
 *   k6 run -e BASE_URL=https://eco-vpp.example.org \
 *          -e INGEST_TOKEN=<token> \
 *          tests/k6/ingest_load.js
 */
import http from 'k6/http'
import { check, sleep } from 'k6'

export const options = {
  thresholds: {
    'http_req_duration': ['p(95)<500', 'p(99)<1500'],
    'http_req_failed':   ['rate<0.005'],
  },
  scenarios: {
    ingest_burst: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 1000,
      stages: [
        { target: 200,  duration: '1m' },
        { target: 1000, duration: '2m' },
        { target: 1000, duration: '5m' },
        { target: 0,    duration: '30s' },
      ],
    },
  },
}

const BASE = __ENV.BASE_URL || 'http://localhost:8000'
const TOKEN = __ENV.INGEST_TOKEN || 'dev-token'

export default function () {
  const did = `did:ethr:volta:0x${(__VU * 1000 + __ITER).toString(16).padStart(8, '0')}`
  const payload = JSON.stringify({
    did,
    voltage: 230 + Math.random(),
    current: Math.random() * 5,
    power_w: Math.random() * 1200,
    energy_kwh: Math.random() * 0.05,
    confidence: 0.95,
  })
  const res = http.post(`${BASE}/api/v1/telemetry/ingest`, payload, {
    headers: { 'Content-Type': 'application/json', 'X-Ingest-Token': TOKEN },
  })
  check(res, { 'ingest 2xx': (r) => r.status === 202 || r.status === 200 })
  sleep(0.01)
}
