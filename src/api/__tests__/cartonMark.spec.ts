import { describe, expect, it, vi } from 'vitest'
import { CARTON_MARK_AUTO_CHECK_TIMEOUT_MS, createCartonMarkApi, type CartonMarkTemplateRecordResponse } from '@/api/cartonMark'

const persistedTemplate: CartonMarkTemplateRecordResponse = {
  id: 'cm-1',
  factory_id: 'huaxing',
  customer_name: 'Dickie',
  po: 'PO-2033',
  item: '2017',
  contract_number: 'SC-88',
  version: 1,
  check_status: '核对通过',
  check_result: {
    excel_file_name: 'customer.xlsx',
    pdf_file_name: 'print.pdf',
    summary: {
      overall_status: '核对通过',
      pass_count: 1,
      changed_count: 0,
      missing_count: 0,
      unexpected_count: 0,
      review_count: 0,
    },
    excel_items: [],
    pdf_items: [],
    comparisons: [],
    extraction: [],
  },
  excel_file_name: 'customer.xlsx',
  excel_file_size: 1200,
  pdf_file_name: 'print.pdf',
  pdf_file_size: 2400,
  created_at: '2026-08-13T10:00:00Z',
  created_by_name: '纸箱仓管',
  qc_ready: true,
}

describe('carton-mark persisted template API', () => {
  it('atomically uploads factory metadata, Excel and print PDF', async () => {
    const post = vi.fn().mockResolvedValue({ data: persistedTemplate })
    const api = createCartonMarkApi({ post } as Parameters<typeof createCartonMarkApi>[0])
    const controller = new AbortController()
    const excel = new File(['excel'], 'customer.xlsx')
    const pdf = new File(['pdf'], 'print.pdf', { type: 'application/pdf' })

    const created = await api.createTemplate({
      factoryId: 'huaxing',
      customerName: 'Dickie',
      item: '2017',
      contractNumber: 'SC-88',
      excelContract: excel,
      printPdf: pdf,
      signal: controller.signal,
    })

    expect(created).toEqual(persistedTemplate)
    expect(post.mock.calls[0]![0]).toBe('/carton-mark/templates')
    const body = post.mock.calls[0]![1] as FormData
    expect(Array.from(body.keys())).toEqual([
      'factory_id',
      'customer_name',
      'item',
      'contract_number',
      'excel_contract',
      'print_pdf',
    ])
    expect(body.get('factory_id')).toBe('huaxing')
    expect(body.get('excel_contract')).toBe(excel)
    expect(body.get('print_pdf')).toBe(pdf)
    expect(post.mock.calls[0]![2]).toEqual({
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
      signal: controller.signal,
    })
  })

  it('lists and reads templates only inside the requested factory', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ data: [persistedTemplate] })
      .mockResolvedValueOnce({ data: persistedTemplate })
    const api = createCartonMarkApi({ get } as Parameters<typeof createCartonMarkApi>[0])

    await expect(api.listTemplates('huaxing')).resolves.toEqual([persistedTemplate])
    await expect(api.getTemplate('cm-1', 'huaxing')).resolves.toEqual(persistedTemplate)
    expect(get).toHaveBeenNthCalledWith(1, '/carton-mark/templates', {
      params: { factory_id: 'huaxing' },
      signal: undefined,
    })
    expect(get).toHaveBeenNthCalledWith(2, '/carton-mark/templates/cm-1', {
      params: { factory_id: 'huaxing' },
      signal: undefined,
    })
  })

  it('downloads documents as authenticated blobs and soft-deletes by factory', async () => {
    const blob = new Blob(['pdf'], { type: 'application/pdf' })
    const get = vi.fn().mockResolvedValue({ data: blob })
    const remove = vi.fn().mockResolvedValue({ status: 204 })
    const api = createCartonMarkApi({ get, delete: remove } as Parameters<typeof createCartonMarkApi>[0])

    await expect(api.downloadTemplateDocument('cm-1', 'print_pdf', 'huaxing')).resolves.toBe(blob)
    await api.deleteTemplate('cm-1', 'huaxing')

    expect(get).toHaveBeenCalledWith('/carton-mark/templates/cm-1/documents/print_pdf', {
      params: { factory_id: 'huaxing' },
      responseType: 'blob',
      signal: undefined,
    })
    expect(remove).toHaveBeenCalledWith('/carton-mark/templates/cm-1', {
      params: { factory_id: 'huaxing' },
      signal: undefined,
    })
  })
})
