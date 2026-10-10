import { afterEach, describe, expect, it } from 'vitest'
import { http } from '@/lib/http'
import { cartonSupplierPortalApi } from '../cartonSupplierPortal'

const originalAdapter = http.defaults.adapter
afterEach(() => { http.defaults.adapter = originalAdapter })

describe('supplier delivery import transport', () => {
  const file = new File(['delivery workbook'], '华康B2026100074.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })

  it('keeps the selected Excel file in multipart form through the shared JSON defaults', async () => {
    http.defaults.adapter = async config => {
      expect(config.url).toBe('/carton-supplier/shipments/import-preview')
      expect(config.data).toBeInstanceOf(FormData)
      expect(config.headers.getContentType()).toBe('multipart/form-data')
      expect((config.data as FormData).get('file')).toBe(file)
      return { data: { sha256: 'preview-hash' }, status: 200, statusText: 'OK', headers: {}, config }
    }
    expect(await cartonSupplierPortalApi.previewDeliveryImport(file)).toEqual({ sha256: 'preview-hash' })
  })

  it('preserves the file, reviewed hash and selected note modes during confirmation', async () => {
    const selections = [{ factory_id: 'huakang-b', delivery_note_no: '2026100074', registration_mode: 'EXISTING_RECEIPT' as const }]
    http.defaults.adapter = async config => {
      expect(config.url).toBe('/carton-supplier/shipments/import-confirm')
      expect(config.data).toBeInstanceOf(FormData)
      expect(config.headers.getContentType()).toBe('multipart/form-data')
      const form = config.data as FormData
      expect(form.get('file')).toBe(file)
      expect(form.get('sha256')).toBe('preview-hash')
      expect(JSON.parse(String(form.get('selections')))).toEqual(selections)
      return { data: { shipments: [] }, status: 200, statusText: 'OK', headers: {}, config }
    }
    await cartonSupplierPortalApi.confirmDeliveryImport(file, {
      filename: file.name, sha256: 'preview-hash', row_count: 1, groups: [],
    }, selections)
  })
})
