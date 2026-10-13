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
  updated_at: '2026-08-13T10:00:00Z',
  created_by_name: '纸箱仓管',
  qc_ready: true,
  manual_released: false,
  manual_release_reason: '',
  manual_release_source_status: '',
  manual_released_by_name: '',
  manual_released_at: '',
}

describe('carton-mark persisted template API', () => {
  it('submits QC originals as multipart with factory, template, stable request and correction identity', async () => {
    const post = vi.fn().mockResolvedValue({ data: [] })
    const api = createCartonMarkApi({ post } as unknown as Parameters<typeof createCartonMarkApi>[0])
    const front = new File(['front'], 'front.png', { type: 'image/png' })
    await api.createQcRecords({ factoryId: 'huaxing', templateId: 'T1', requestId: 'retry-same',
      mode: 'batch', note: '重新印刷已完成', correctsRecordId: 'QC-old', frontPhotos: [front], sidePhotos: [] })
    const [url, body, config] = post.mock.calls[0]!
    expect(url).toBe('/carton-mark/qc-records')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('factory_id')).toBe('huaxing')
    expect(body.get('template_id')).toBe('T1')
    expect(body.get('request_id')).toBe('retry-same')
    expect(body.get('corrects_record_id')).toBe('QC-old')
    expect(body.get('front_photos')).toBe(front)
    expect(body.has('result')).toBe(false)
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
  })
  it('loads and maintains the independent factory carton-mark customer library', async () => {
    const customers = [
      {
        id: 'CMC-DICKIE',
        factory_id: 'huaxing',
        name: 'Dickie',
        revision: 1,
        created_by: 'manager',
        created_by_name: '纸箱经理',
        created_at: '2026-08-19T09:00:00+08:00',
        updated_by: 'manager',
        updated_by_name: '纸箱经理',
        updated_at: '2026-08-19T09:00:00+08:00',
      },
    ]
    const get = vi.fn().mockResolvedValue({ data: customers })
    const post = vi.fn().mockResolvedValue({ data: customers[0] })
    const put = vi.fn().mockResolvedValue({ data: { ...customers[0], name: 'Dickie Toys', revision: 2 } })
    const remove = vi.fn().mockResolvedValue({ status: 204 })
    const api = createCartonMarkApi({ get, post, put, delete: remove } as Parameters<typeof createCartonMarkApi>[0])
    const controller = new AbortController()

    await expect(api.listCustomers('huaxing', controller.signal)).resolves.toEqual(customers)
    expect(get).toHaveBeenCalledWith('/carton-mark/customers', {
      params: { factory_id: 'huaxing' },
      signal: controller.signal,
    })
    await api.createCustomer('huaxing', 'Dickie')
    expect(post).toHaveBeenCalledWith('/carton-mark/customers', { name: 'Dickie' }, {
      params: { factory_id: 'huaxing' },
    })
    await api.updateCustomer('huaxing', 'CMC-DICKIE', 'Dickie Toys', 1)
    expect(put).toHaveBeenCalledWith('/carton-mark/customers/CMC-DICKIE', {
      name: 'Dickie Toys',
      revision: 1,
    }, {
      params: { factory_id: 'huaxing' },
    })
    await api.deleteCustomer('huaxing', 'CMC-DICKIE', 2)
    expect(remove).toHaveBeenCalledWith('/carton-mark/customers/CMC-DICKIE', {
      params: { factory_id: 'huaxing', revision: 2 },
    })
  })

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

  it('rechecks the stored Excel and PDF inside the requested factory', async () => {
    const post = vi.fn().mockResolvedValue({ data: persistedTemplate })
    const api = createCartonMarkApi({ post } as Parameters<typeof createCartonMarkApi>[0])
    const controller = new AbortController()

    await expect(api.recheckTemplate('cm-1', 'huaxing', controller.signal)).resolves.toEqual(persistedTemplate)
    expect(post).toHaveBeenCalledWith('/carton-mark/templates/cm-1/recheck', undefined, {
      params: { factory_id: 'huaxing' },
      timeout: CARTON_MARK_AUTO_CHECK_TIMEOUT_MS,
      signal: controller.signal,
    })
  })

  it('manually releases a checked template with an auditable reason', async () => {
    const releasedTemplate = {
      ...persistedTemplate,
      check_status: '发现差异',
      qc_ready: true,
      manual_released: true,
      manual_release_reason: '已核对客户确认的允许差异',
      manual_release_source_status: '发现差异',
      manual_released_by_name: '纸箱主管',
      manual_released_at: '2026-08-25T10:00:00+08:00',
    }
    const post = vi.fn().mockResolvedValue({ data: releasedTemplate })
    const api = createCartonMarkApi({ post } as Parameters<typeof createCartonMarkApi>[0])
    const controller = new AbortController()

    await expect(api.manualReleaseTemplate(
      'cm-1',
      'huaxing',
      '已核对客户确认的允许差异',
      controller.signal,
    )).resolves.toEqual(releasedTemplate)
    expect(post).toHaveBeenCalledWith('/carton-mark/templates/cm-1/manual-release', {
      reason: '已核对客户确认的允许差异',
    }, {
      params: { factory_id: 'huaxing' },
      signal: controller.signal,
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
