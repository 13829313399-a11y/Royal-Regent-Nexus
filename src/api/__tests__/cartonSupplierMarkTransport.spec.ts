import { afterEach, describe, expect, it } from 'vitest'
import { http } from '@/lib/http'
import { cartonSupplierPortalApi } from '../cartonSupplierPortal'

const originalAdapter = http.defaults.adapter
afterEach(() => { http.defaults.adapter = originalAdapter })
const identifiers = { factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a', excel_asset_id: 'excel-a', expected_revision: 3 }
function capture(expected: Record<string, string>, fileNames: string[]) {
  http.defaults.adapter = async config => {
    // Exercise real shared defaults, request interceptors and Axios transform;
    // mocking http.post misses FormData being converted into a JSON string.
    expect(config.data).toBeInstanceOf(FormData)
    expect(config.headers.getContentType()).not.toContain('application/json')
    const body = config.data as FormData
    for (const [key, value] of Object.entries(expected)) expect(body.get(key)).toBe(value)
    expect(Array.from(body.values()).filter(value => value instanceof File).map(value => (value as File).name)).toEqual(fileNames)
    return { data: {}, status: 201, statusText: 'Created', headers: {}, config }
  }
}

describe('supplier carton-mark request serialization', () => {
  it('reads selected source sheets once and rerenders signed review data as multipart', async () => {
    const file = new File(['excel'], 'read.xlsx')
    const paths: string[] = []
    http.defaults.adapter = async config => {
      paths.push(config.url!); const body = config.data as FormData
      expect(body).toBeInstanceOf(FormData); expect(body.get('excel')).toBe(file)
      expect(body.has('order_id')).toBe(false)
      if (config.url?.endsWith('read-pdf-draft')) { expect(body.get('ai_consent')).toBe('true'); expect(body.get('worksheets_json')).toBe('["SM"]') }
      else { expect(body.get('review_payload')).toBe('signed'); expect(body.has('ai_consent')).toBe(false); expect(body.get('edits_json')).toBe('{"r0p0f0":"2.5 KGS"}'); expect(body.get('include_sources')).toBe('false') }
      return { data: new Blob(['pdf']), status: 200, statusText: 'OK', headers: {}, config }
    }
    await cartonSupplierPortalApi.readMarkPdfDraft({ excel: file, worksheets: ['SM'] })
    const review = { payload: 'signed', signature: 'proof' } as Parameters<typeof cartonSupplierPortalApi.renderReviewedMarkDraft>[1]
    await cartonSupplierPortalApi.renderReviewedMarkDraft({ excel: file }, review, { edits: { r0p0f0: '2.5 KGS' }, reviewed_notes: [], paper: 'A3', orientation: 'portrait', include_sources:false })
    expect(paths).toEqual(['/carton-supplier/carton-mark/read-pdf-draft', '/carton-supplier/carton-mark/render-reviewed-draft'])
  })
  it('exports an upload as a draft without serializing factory or purchase order identifiers', async () => {
    const file = new File(['excel'], 'draft.xlsx')
    http.defaults.adapter = async config => {
      expect(config.url).toBe('/carton-supplier/carton-mark/generate-pdf-draft')
      expect(config.responseType).toBe('blob')
      const body = config.data as FormData
      expect(body).toBeInstanceOf(FormData)
      expect(body.get('excel')).toBe(file); expect(body.get('engine')).toBe('excel_original')
      expect(body.has('factory_id')).toBe(false); expect(body.has('order_id')).toBe(false)
      expect(config.headers.getContentType()).not.toContain('application/json')
      return { data: new Blob(['pdf']), status: 200, statusText: 'OK', headers: {
        'x-carton-pdf-pages': '2', 'x-carton-pdf-warnings': encodeURIComponent(JSON.stringify(['未关联'])) }, config }
    }
    const result = await cartonSupplierPortalApi.generateMarkPdfDraft({ excel: file, engine: 'excel_original' })
    expect(result.page_count).toBe(2); expect(result.warnings).toEqual(['未关联'])
    expect(result.file_name).toBe('draft_审阅稿.pdf')
  })
  it('scopes the DeepSeek status lookup to the exact factory and issued order', async () => {
    http.defaults.adapter = async config => {
      expect(config.url).toBe('/carton-supplier/carton-mark/pdf-ai-status')
      expect(config.params).toEqual({ factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a' })
      return { data: { available: true }, status: 200, statusText: 'OK', headers: {}, config }
    }
    expect((await cartonSupplierPortalApi.markPdfAiStatus('huaxing', { id: 'order-a', issue_id: 'issue-a' })).available).toBe(true)
  })
  it('sends atomic association targets and the replay key as multipart without legacy regular-order assumptions', async () => {
    const targets = [{ order_kind: 'MISC' as const, order_id: 'misc', expected_revision: 3, issue_id: 'version-3', line_id: '' }]
    capture({ factory_id: 'huaxing', shared_unbound: 'true', request_id: 'upload-123', targets_json: JSON.stringify(targets) }, ['photo.png'])
    await cartonSupplierPortalApi.uploadMarkAssets('huaxing', [new File(['image'], 'photo.png')], undefined, undefined, true, { request_id: 'upload-123', targets })
  })
  it('saves customer layout rules, previous version and historical PDF as multipart fields', async () => {
    const config = { mode: 'front_side' as const, paper: 'A4' as const, font: 'Helvetica' as const, font_size: 11, front_percent: 55, front_copies: 2, side_copies: 2, barcode: 'none' as const, side_address: '', instructions: '', reference_page: 0, logo_region: null, stamp_region: null, field_cells: {} }
    capture({ factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a', name: 'BUZZ', expected_version: '0', config: JSON.stringify(config) }, ['old.pdf'])
    await cartonSupplierPortalApi.saveMarkLayout('huaxing', { id: 'order-a', issue_id: 'issue-a', contract_no: 'CONTRACT', customer_name: 'BUZZ', customer_po: '', item_no: 'ITEM' }, 'BUZZ', config, null, new File(['pdf'], 'old.pdf'))
  })
  it('sends the exact order and source revision as JSON for PDF generation', async () => {
    http.defaults.adapter = async config => {
      expect(config.url).toBe('/carton-supplier/carton-mark/generate-pdf')
      expect(config.headers.getContentType()).toContain('application/json')
      expect(JSON.parse(config.data as string)).toEqual({ ...identifiers, layout_id: 'layout-a' })
      expect(config.timeout).toBe(360000)
      return { data: { asset: { id: 'pdf-a' }, page_count: 1, warnings: [] }, status: 201, statusText: 'Created', headers: {}, config }
    }
    expect((await cartonSupplierPortalApi.generateMarkPdf({ ...identifiers, layout_id: 'layout-a' })).page_count).toBe(1)
  })
  it('keeps the stored Excel/PDF identifiers as form fields when no new file is uploaded', async () => {
    capture({ factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a', excel_asset_id: 'excel-a', expected_revision: '3', pdf_asset_id: 'pdf-a', expected_pdf_revision: '2' }, [])
    await cartonSupplierPortalApi.createMarkCheck({ ...identifiers, pdf_asset_id: 'pdf-a', expected_pdf_revision: 2 })
  })
  it('sends both the new print PDF and every binding identifier without JSON conversion', async () => {
    capture({ factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a', excel_asset_id: 'excel-a', expected_revision: '3' }, ['print.pdf'])
    await cartonSupplierPortalApi.createMarkCheck({ ...identifiers, print_pdf: new File(['%PDF-1.4'], 'print.pdf', { type: 'application/pdf' }) })
  })
  it('preserves mixed original files and explicit order/issue fields for batch upload', async () => {
    capture({ factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a' }, ['customer.xlsx', 'print.pdf', 'photo.png'])
    await cartonSupplierPortalApi.uploadMarkAssets('huaxing', [new File(['excel'], 'customer.xlsx'), new File(['%PDF-1.4'], 'print.pdf'), new File(['image'], 'photo.png')],
      { id: 'order-a', issue_id: 'issue-a', contract_no: 'CONTRACT', customer_name: 'BUZZ', customer_po: 'PO', item_no: 'ITEM' })
  })
})
