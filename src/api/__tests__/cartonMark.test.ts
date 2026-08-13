import assert from 'node:assert/strict'
import {
  CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
  createCartonMarkApi,
  type CartonMarkDocumentContentCheckResponse,
} from '../cartonMark.js'

const calls: Array<{ method: string, url: string, data?: unknown, config?: unknown }> = []

const documentCheckResponse: CartonMarkDocumentContentCheckResponse = {
  excel_file_name: 'customer-mark.xlsx',
  pdf_file_name: 'print-mark.pdf',
  summary: {
    overall_status: '核对通过',
    pass_count: 1,
    changed_count: 0,
    missing_count: 0,
    unexpected_count: 0,
    review_count: 0,
  },
  excel_items: [{ text: 'PO 2033', location: '箱唛!A1' }],
  pdf_items: [{ text: 'PO 2033', location: '第 1 页' }],
  comparisons: [{
    status: 'pass',
    expected: 'PO 2033',
    actual: 'PO 2033',
    expected_location: '箱唛!A1',
    actual_location: '第 1 页',
    note: '',
  }],
  extraction: [],
}

const client = {
  async post(url: string, data?: unknown, config?: unknown) {
    calls.push({ method: 'post', url, data, config })
    if (url === '/carton-mark/document-content-check') {
      return {
        data: documentCheckResponse,
      }
    }
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

const documentResult = await api.documentContentCheck({
  excelContract: new Blob(['excel'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
  printPdf: new Blob(['pdf'], { type: 'application/pdf' }),
})

assert.equal(documentResult.summary.overall_status, '核对通过')
assert.equal(documentResult.excel_file_name, 'customer-mark.xlsx')
assert.equal(documentResult.pdf_file_name, 'print-mark.pdf')
assert.equal(calls[0]?.url, '/carton-mark/document-content-check')
const documentRequest = calls[0]
assert.ok(documentRequest?.data instanceof FormData)
const documentFormData = documentRequest.data as FormData
assert.deepEqual(Array.from(documentFormData.keys()), [
  'excel_contract',
  'print_pdf',
])
assert.ok(documentFormData.get('excel_contract') instanceof Blob)
assert.ok(documentFormData.get('print_pdf') instanceof Blob)
assert.deepEqual(documentRequest.config, {
  headers: {
    'Content-Type': 'multipart/form-data',
  },
  timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
})

const result = await api.autoCheck({
  customerName: 'Dickie',
  po: '2033',
  item: '2017',
  pdfTemplate: new Blob(['pdf'], { type: 'application/pdf' }),
  frontPhoto: new Blob(['front'], { type: 'image/png' }),
  sidePhoto: new Blob(['side'], { type: 'image/png' }),
})

assert.equal(result.summary.overall_status, '需复核')
assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
  'post /carton-mark/document-content-check',
  'post /carton-mark/auto-check',
])

const request = calls[1]
assert.ok(request.data instanceof FormData)
const qaFormData = request.data as FormData
assert.deepEqual(Array.from(qaFormData.keys()), [
  'customer_name',
  'po',
  'item',
  'pdf_template',
  'front_photo',
  'side_photo',
])
assert.equal(qaFormData.get('customer_name'), 'Dickie')
assert.equal(qaFormData.get('po'), '2033')
assert.equal(qaFormData.get('item'), '2017')
assert.ok(qaFormData.get('pdf_template') instanceof Blob)
assert.ok(qaFormData.get('front_photo') instanceof Blob)
assert.ok(qaFormData.get('side_photo') instanceof Blob)
assert.equal(qaFormData.has('excel_contract'), false)
assert.equal(qaFormData.has('print_pdf'), false)
assert.deepEqual(request.config, {
  headers: {
    'Content-Type': 'multipart/form-data',
  },
  timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
})
