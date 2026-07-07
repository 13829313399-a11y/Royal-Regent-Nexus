import assert from 'node:assert/strict'
import { CARTON_MARK_AUTO_CHECK_TIMEOUT_MS, createCartonMarkApi } from '../cartonMark.js'

const calls: Array<{ method: string, url: string, data?: unknown, config?: unknown }> = []

const client = {
  async post(url: string, data?: unknown, config?: unknown) {
    calls.push({ method: 'post', url, data, config })
    return {
      data: {
        summary: {
          overall_status: '需复核',
          pass_count: 0,
          mismatch_count: 0,
          missing_count: 0,
          review_count: 1,
        },
        template_fields: [],
        front_template_fields: [],
        side_template_fields: [],
        front_photo_fields: [],
        side_photo_fields: [],
        comparisons: [],
        extraction: [],
      },
    }
  },
}

const api = createCartonMarkApi(client as Parameters<typeof createCartonMarkApi>[0])

const result = await api.autoCheck({
  customerName: 'Dicky',
  po: '2033',
  item: '2017',
  pdfTemplate: new Blob(['pdf'], { type: 'application/pdf' }),
  frontPhoto: new Blob(['front'], { type: 'image/png' }),
  sidePhoto: new Blob(['side'], { type: 'image/png' }),
})

assert.equal(result.summary.overall_status, '需复核')
assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
  'post /carton-mark/auto-check',
])

const request = calls[0]
assert.ok(request.data instanceof FormData)
assert.equal((request.data as FormData).get('customer_name'), 'Dicky')
assert.equal((request.data as FormData).get('po'), '2033')
assert.equal((request.data as FormData).get('item'), '2017')
assert.deepEqual(request.config, {
  headers: {
    'Content-Type': 'multipart/form-data',
  },
  timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
})
