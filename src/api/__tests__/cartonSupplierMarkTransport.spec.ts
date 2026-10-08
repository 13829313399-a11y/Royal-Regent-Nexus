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
