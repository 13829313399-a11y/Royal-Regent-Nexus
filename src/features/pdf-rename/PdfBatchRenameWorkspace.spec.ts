import { DOMWrapper, mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PdfRenamePreviewResult, PdfRenameRuleDefinition } from '@/api/pdfRename'
import PdfBatchRenameWorkspace from './PdfBatchRenameWorkspace.vue'

const api = vi.hoisted(() => ({ getPdfRenameRules: vi.fn(), previewPdfRename: vi.fn(), executePdfRename: vi.fn() }))
const download = vi.hoisted(() => vi.fn())
vi.mock('@/api/pdfRename', () => ({ pdfRenameApi: api, PdfRenameApiError: class extends Error {} }))
vi.mock('./pdfRenameUtils', async (importOriginal) => ({ ...await importOriginal<typeof import('./pdfRenameUtils')>(), downloadToolBlob: download }))
vi.mock('@/features/document-tools/PdfCanvas.vue', () => ({ default: {
  name: 'PdfCanvas', props: ['url', 'pageIndex'], emits: ['page'],
  template: '<section data-testid="source-pdf-canvas"><button type="button" @click="$emit(\'page\', pageIndex + 1)">下一页</button></section>',
} }))

const rule: PdfRenameRuleDefinition = {
  id: 'buzzbee-inspection', label: 'BuzzBee 行验报告', version: '1.0.1', status: 'active', available: true,
  description: '生成 #货号-PO+PO.pdf；按报告顺序保留全部 PO。', regions: [], setup_checklist: [],
  factory_ids: ['huaxing'],
}
const result: PdfRenamePreviewResult = {
  rule, preview_token: 'review-1', summary: { total: 1, ready: 0, review: 1, error: 0 },
  items: [{ source_file_name: 'scan.pdf', interval_name: '#11001-52140+52141',
    target_file_name: '#11001-52140+52141.pdf', status: 'REVIEW', issues: [], fields: [
      { key: 'item_no', label: '货号', raw_text: 'Item No./Description:-11001/PRODUCT', normalized_text: '11001', route: 'LOCAL_OCR', confidence: .8 },
      { key: 'po_numbers', label: 'PO（报告顺序）', raw_text: 'S/C:-52140+52141', normalized_text: '52140+52141', route: 'LOCAL_OCR', confidence: .8 },
    ] }],
}
const wrappers: ReturnType<typeof mount>[] = []
const mountHosts: HTMLElement[] = []

beforeEach(() => {
  vi.clearAllMocks()
  api.getPdfRenameRules.mockResolvedValue({ rules: [rule], limits: { max_files: 50, max_batch_bytes: 200 * 1024 * 1024, max_file_bytes: 20 * 1024 * 1024 } })
  api.previewPdfRename.mockResolvedValue(structuredClone(result))
  api.executePdfRename.mockResolvedValue({ blob: new Blob(['zip']), fileName: 'results.zip', fileCount: 1 })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  mountHosts.splice(0).forEach(host => host.remove())
  vi.unstubAllGlobals()
})

async function setup(attach = false) {
  const host = attach ? document.createElement('div') : undefined
  if (host) { document.body.appendChild(host); mountHosts.push(host) }
  const wrapper = mount(PdfBatchRenameWorkspace, { attachTo: host, props: { contextLabel: '华兴厂区', factoryId: 'huaxing' } })
  wrappers.push(wrapper)
  await flushPromises()
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['%PDF-scan'], 'scan.pdf', { type: 'application/pdf' })] })
  await input.trigger('change')
  return wrapper
}
function button(wrapper: Awaited<ReturnType<typeof setup>>, label: string) {
  const found = wrapper.findAll('button').find(node => node.text().includes(label))
  if (!found) throw new Error(`Missing button: ${label}`)
  return found
}

function partialCaixingResult(missing = ['report_no']): PdfRenamePreviewResult {
  const caixing = { ...rule, id: 'caixing-inspection', label: '彩星行验报告' }
  return {
    rule: caixing, preview_token: 'caixing-partial', summary: { total: 1, ready: 0, review: 0, error: 1 },
    items: [{ source_file_name: 'scan.pdf', target_file_name: '', interval_name: '', status: 'ERROR',
      filename_template: '{report_no}-#{item_no}-{po_numbers}-{quantity}-{report_date}.pdf',
      manual_override_allowed: true,
      issues: [{ code: 'PDF_RENAME_INTERVAL_INVALID', message: 'Batch no. 的值模糊，请人工核对。' }],
      fields: [
        ['report_no', '报告号（Batch no.）', 'RR6015P'],
        ['item_no', '货号（Item number 前 5 位）', '57812'],
        ['po_numbers', 'PO 号（P/O no.）', '1931771'],
        ['quantity', '数量（Pcs）', '2800'],
        ['report_date', '日期（DATE，月/日/年）', '2026.3.4'],
      ].map(([key, label, text]) => ({ key: key!, label: label!, raw_text: text!,
        normalized_text: missing.includes(key!) ? '' : text!,
        validation_error: missing.includes(key!) ? '请核对原 PDF 后补充此项。' : '',
        route: 'LOCAL_OCR', confidence: .99 })),
    }],
  }
}

describe('BuzzBee batch rename review workflow', () => {
  it('previews the uploaded original and applies a missing field in the same window without losing edits', async () => {
    const createUrl = vi.fn().mockReturnValueOnce('blob:source-1').mockReturnValueOnce('blob:source-2')
    const revokeUrl = vi.fn()
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createUrl; static revokeObjectURL = revokeUrl })
    const partial = partialCaixingResult()
    const corrected = structuredClone(partial)
    corrected.items[0]!.status = 'REVIEW'
    corrected.items[0]!.manual_override = true
    corrected.items[0]!.target_file_name = 'RR6015P-#57812-1931771-2800-2026.3.4.pdf'
    corrected.summary = { total: 1, ready: 0, review: 1, error: 0 }
    api.getPdfRenameRules.mockResolvedValueOnce({ rules: [partial.rule], limits: {} })
    api.previewPdfRename.mockResolvedValueOnce(partial).mockResolvedValueOnce(corrected)
    const wrapper = await setup(true)
    const file = wrapper.get<HTMLInputElement>('input[type="file"]').element.files![0]!
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(createUrl).not.toHaveBeenCalled()
    const opener = wrapper.get<HTMLButtonElement>('button[aria-label="预览 scan.pdf"]')
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()
    const dialog = new DOMWrapper(document.querySelector<HTMLElement>('[role="dialog"]')!)
    expect(dialog.text()).toContain('原 PDF 预览与补充')
    expect(createUrl).toHaveBeenCalledWith(file)
    expect(api.previewPdfRename).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(dialog.get('button[aria-label="关闭原 PDF 预览"]').element)
    const viewer = wrapper.findComponent({ name: 'PdfCanvas' })
    expect(viewer.props('url')).toBe('blob:source-1')
    await dialog.get('[data-testid="source-pdf-canvas"] button').trigger('click')
    expect(viewer.props('pageIndex')).toBe(1)
    await dialog.get('input[aria-label="补充 报告号（Batch no.） scan.pdf"]').setValue('RR6015P')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="补充 报告号（Batch no.） scan.pdf"]').element.value).toBe('RR6015P')
    expect(dialog.text()).toContain(corrected.items[0]!.target_file_name)
    await dialog.get('input[aria-label="确认人工改名 scan.pdf"]').setValue(true)
    await dialog.findAll('button').find(node => node.text() === '应用修改并重新预览')!.trigger('click')
    await flushPromises()
    expect(api.previewPdfRename).toHaveBeenLastCalledWith(expect.any(Array), 'caixing-inspection', 'huaxing', expect.any(AbortSignal), [
      { source_index: 0, target_file_name: corrected.items[0]!.target_file_name, confirmed: true },
    ])
    expect(createUrl).toHaveBeenCalledTimes(1)
    await dialog.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(revokeUrl).toHaveBeenCalledWith('blob:source-1')
    expect(document.activeElement).toBe(opener.element)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="补充 报告号（Batch no.） scan.pdf"]').element.value).toBe('RR6015P')
    await opener.trigger('click')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'PdfCanvas' }).props('pageIndex')).toBe(0)
    await wrapper.setProps({ factoryId: 'huadeng' })
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(revokeUrl.mock.calls).toEqual([['blob:source-1'], ['blob:source-2']])
  })

  it('matches previews and corrections by row even when two original filenames are identical', async () => {
    const createUrl = vi.fn().mockReturnValue('blob:source')
    const revokeUrl = vi.fn()
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createUrl; static revokeObjectURL = revokeUrl })
    const partial = partialCaixingResult()
    partial.items.push(structuredClone(partial.items[0]!))
    partial.summary = { total: 2, ready: 0, review: 0, error: 2 }
    api.getPdfRenameRules.mockResolvedValueOnce({ rules: [partial.rule], limits: {} })
    api.previewPdfRename.mockResolvedValueOnce(partial)
    const wrapper = await setup()
    const fileInput = wrapper.get<HTMLInputElement>('input[type="file"]')
    const first = fileInput.element.files![0]!
    const second = new File(['%PDF-second-source'], 'scan.pdf', { type: 'application/pdf', lastModified: 1 })
    Object.defineProperty(fileInput.element, 'files', { configurable: true, value: [second] })
    await fileInput.trigger('change')
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    await wrapper.findAll('button[aria-label="预览 scan.pdf"]')[1]!.trigger('click')
    await flushPromises()
    const dialog = new DOMWrapper(document.querySelector<HTMLElement>('[role="dialog"]')!)
    expect(createUrl).toHaveBeenLastCalledWith(second)
    await dialog.get('input[aria-label="补充 报告号（Batch no.） scan.pdf"]').setValue('RR6016')
    const rowInputs = wrapper.findAll<HTMLInputElement>('input[aria-label="补充 报告号（Batch no.） scan.pdf"]')
    expect(rowInputs.map(node => node.element.value)).toEqual(['', 'RR6016'])
    await dialog.get('button[aria-label="关闭原 PDF 预览"]').trigger('click')
    await flushPromises()
    await wrapper.findAll('button[aria-label="预览 scan.pdf"]')[0]!.trigger('click')
    await flushPromises()
    expect(createUrl).toHaveBeenLastCalledWith(first)
    wrapper.unmount()
    expect(revokeUrl).toHaveBeenCalledTimes(2)
  })

  it('completes only the unclear Batch no., keeps all other values and downloads the assembled name', async () => {
    const partial = partialCaixingResult()
    const name = 'RR6015P-#57812-1931771-2800-2026.3.4.pdf'
    const enteredName = 'ＲＲ６０１５Ｐ-#57812-1931771-2800-2026.3.4.pdf'
    const corrected = structuredClone(partial)
    corrected.preview_token = 'caixing-corrected'
    corrected.summary = { total: 1, ready: 0, review: 1, error: 0 }
    corrected.items[0]!.status = 'REVIEW'
    corrected.items[0]!.manual_override = true
    corrected.items[0]!.target_file_name = name
    // Rechecking the PDF must not replace values already used in the manual name.
    corrected.items[0]!.fields.find(field => field.key === 'po_numbers')!.normalized_text = '9999999'
    api.getPdfRenameRules.mockResolvedValueOnce({ rules: [partial.rule], limits: {} })
    api.previewPdfRename.mockResolvedValueOnce(partial).mockResolvedValueOnce(corrected)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('input[aria-label^="补充 "]')).toHaveLength(1)
    expect(wrapper.find('input[aria-label="人工文件名 scan.pdf"]').exists()).toBe(false)
    for (const value of ['57812', '1931771', '2800', '2026.3.4']) expect(wrapper.text()).toContain(value)
    expect(wrapper.text()).toContain('【待补充：报告号（Batch no.）】-#57812-1931771-2800-2026.3.4.pdf')
    const input = wrapper.get('input[aria-label="补充 报告号（Batch no.） scan.pdf"]')
    await input.setValue('ＲＲ６０１５Ｐ')
    expect(wrapper.text()).toContain(enteredName)
    expect(wrapper.text()).not.toContain('【待补充：')
    expect(button(wrapper, '应用补充').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="确认人工改名 scan.pdf"]').setValue(true)
    await button(wrapper, '应用补充').trigger('click')
    await flushPromises()
    const overrides = [{ source_index: 0, target_file_name: enteredName, confirmed: true }]
    expect(api.previewPdfRename).toHaveBeenLastCalledWith(expect.any(Array), 'caixing-inspection', 'huaxing', expect.any(AbortSignal), overrides)
    expect(wrapper.text()).toContain(name)
    expect(wrapper.text()).not.toContain('9999999')
    expect(wrapper.text()).toContain('人工补充 · 待最终复核')
    await wrapper.get('aside input[type="checkbox"]').setValue(true)
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await flushPromises()
    expect(api.executePdfRename).toHaveBeenLastCalledWith(expect.any(Array), 'caixing-inspection', 'caixing-corrected', true, 'huaxing', expect.any(AbortSignal), overrides)
    expect(download).toHaveBeenCalledOnce()
    await input.setValue('RR6016')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="确认人工改名 scan.pdf"]').element.checked).toBe(false)
    expect(wrapper.get<HTMLInputElement>('aside input[type="checkbox"]').element.checked).toBe(false)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    await input.setValue('')
    expect(wrapper.text()).toContain('【待补充：报告号（Batch no.）】')
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
  })

  it('requires every missing field before applying, without requesting clear fields again', async () => {
    const partial = partialCaixingResult(['report_no', 'quantity'])
    api.getPdfRenameRules.mockResolvedValueOnce({ rules: [partial.rule], limits: {} })
    api.previewPdfRename.mockResolvedValueOnce(partial)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('input[aria-label^="补充 "]')).toHaveLength(2)
    await wrapper.get('input[aria-label="补充 报告号（Batch no.） scan.pdf"]').setValue('RR6015P')
    expect(wrapper.text()).toContain('RR6015P-#57812-1931771-【待补充：数量（Pcs）】-2026.3.4.pdf')
    expect(wrapper.get('#rename-download-blockers').text()).toContain('请补齐标记的未识别字段')
    expect(wrapper.find('input[aria-label="确认人工改名 scan.pdf"]').exists()).toBe(false)
    expect(button(wrapper, '应用补充').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="补充 数量（Pcs） scan.pdf"]').setValue('2800')
    expect(wrapper.text()).toContain('RR6015P-#57812-1931771-2800-2026.3.4.pdf')
    await wrapper.get('input[aria-label="确认人工改名 scan.pdf"]').setValue(true)
    expect(button(wrapper, '应用补充').attributes('disabled')).toBeUndefined()
    await wrapper.setProps({ factoryId: 'huadeng' })
    await wrapper.setProps({ factoryId: 'huaxing' })
    await flushPromises()
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('RR6015P')
  })

  it('selects BuzzBee Indonesia invoices and downloads the invoice filename', async () => {
    const invoiceRule: PdfRenameRuleDefinition = {
      ...rule, id: 'buzzbee-indonesia-invoice', label: 'BuzzBee印尼发票',
      description: '识别红色发票号，生成 客发票--发票号.pdf。',
    }
    api.getPdfRenameRules.mockResolvedValueOnce({ rules: [rule, invoiceRule], limits: {} })
    const invoice = structuredClone(result)
    invoice.rule = invoiceRule
    invoice.items[0]!.interval_name = '客发票--104753'
    invoice.items[0]!.target_file_name = '客发票--104753.pdf'
    invoice.items[0]!.fields = [{ key: 'invoice_number', label: '红色发票号',
      raw_text: '104753', normalized_text: '104753', route: 'LOCAL_OCR', confidence: .8 }]
    api.previewPdfRename.mockResolvedValueOnce(invoice)
    const wrapper = await setup()
    expect(wrapper.get('select').text()).toContain('BuzzBee印尼发票')
    await wrapper.get('select').setValue(invoiceRule.id)
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(api.previewPdfRename).toHaveBeenCalledWith(expect.any(Array), invoiceRule.id, 'huaxing', expect.any(AbortSignal), [])
    expect(wrapper.text()).toContain('客发票--104753.pdf')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await flushPromises()
    expect(api.executePdfRename).toHaveBeenCalledWith(expect.any(Array), invoiceRule.id, 'review-1', true, 'huaxing', expect.any(AbortSignal), [])
    expect(download).toHaveBeenCalledOnce()
  })

  it('downloads a validated scan without a review checkbox or required manual name', async () => {
    const ready = structuredClone(result)
    ready.summary = { total: 1, ready: 1, review: 0, error: 0 }
    ready.items[0]!.status = 'READY'
    api.previewPdfRename.mockResolvedValueOnce(ready)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('可执行 1')
    expect(wrapper.text()).toContain('修改文件名（可选）')
    expect(wrapper.text()).not.toContain('人工改名并放行')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeUndefined()
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await flushPromises()
    expect(api.executePdfRename).toHaveBeenCalledWith(expect.any(Array), 'buzzbee-inspection', 'review-1', false, 'huaxing', expect.any(AbortSignal), [])
    expect(download).toHaveBeenCalledOnce()
  })

  it('shows the configured Qwen mode and actual per-field recognition source', async () => {
    api.getPdfRenameRules.mockResolvedValueOnce({ rules: [rule], limits: {}, recognition: {
      mode: 'qwen', label: '千问识别', description: '使用已配置的千问识别命名区域。',
    } })
    const ready = structuredClone(result)
    ready.summary = { total: 1, ready: 1, review: 0, error: 0 }
    ready.items[0]!.status = 'READY'
    ready.items[0]!.fields.forEach(field => { field.route = 'QWEN'; field.confidence = null })
    api.previewPdfRename.mockResolvedValueOnce(ready)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('千问识别')
    expect(wrapper.text()).toContain('仅将命名所需的首页区域发送给已配置的千问')
    expect(wrapper.text()).not.toContain('本地扫描识别')
    expect(wrapper.text()).not.toContain('PDF 文字')
  })

  it('selects Caixing independently, shows all five fields and downloads with its rule id', async () => {
    const caixing: PdfRenameRuleDefinition = { ...rule, id: 'caixing-inspection', label: '彩星行验报告',
      version: '1.0.0', description: '报告号-#货号-PO号-数量-日期.pdf；报告号取 Batch no.。' }
    api.getPdfRenameRules.mockResolvedValue({ rules: [rule, caixing], limits: { max_files: 50, max_batch_bytes: 200 * 1024 * 1024, max_file_bytes: 20 * 1024 * 1024 } })
    const caixingResult = structuredClone(result)
    caixingResult.rule = caixing
    caixingResult.preview_token = 'caixing-review'
    caixingResult.items[0]!.target_file_name = 'RR6015P-#57812-1931771-2800-2026.3.4.pdf'
    caixingResult.items[0]!.fields = [
      ['report_no', '报告号（Batch no.）', 'RR6015P'],
      ['item_no', '货号（Item number 前 5 位）', '57812'],
      ['po_numbers', 'PO 号（P/O no.）', '1931771'],
      ['quantity', '数量（Pcs）', '2800'],
      ['report_date', '日期（DATE，月/日/年）', '2026.3.4'],
    ].map(([key, label, text]) => ({ key: key!, label: label!, normalized_text: text!, raw_text: text!, route: 'LOCAL_OCR', confidence: .99 }))
    api.previewPdfRename.mockResolvedValue(caixingResult)
    const wrapper = await setup()
    await wrapper.get('select').setValue('caixing-inspection')
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(api.previewPdfRename).toHaveBeenCalledWith(expect.any(Array), 'caixing-inspection', 'huaxing', expect.any(AbortSignal), [])
    for (const label of ['报告号（Batch no.）', '数量（Pcs）', '日期（DATE，月/日/年）']) expect(wrapper.text()).toContain(label)
    expect(wrapper.text()).toContain('RR6015P-#57812-1931771-2800-2026.3.4.pdf')
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await flushPromises()
    expect(api.executePdfRename).toHaveBeenCalledWith(expect.any(Array), 'caixing-inspection', 'caixing-review', true, 'huaxing', expect.any(AbortSignal), [])
    expect(download).toHaveBeenCalledOnce()
    await wrapper.setProps({ factoryId: 'huadeng', contextLabel: '华灯厂区' })
    await flushPromises()
    expect(wrapper.find('option[value="caixing-inspection"]').exists()).toBe(false)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('selects the active rule, displays identifiers/evidence and gates ZIP on review', async () => {
    const wrapper = await setup()
    expect(wrapper.get('select').element.value).toBe('buzzbee-inspection')
    expect(wrapper.text()).not.toContain('等待首个业务规则')
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(api.previewPdfRename).toHaveBeenCalledWith(expect.any(Array), 'buzzbee-inspection', 'huaxing', expect.any(AbortSignal), [])
    expect(wrapper.text()).toContain('PO（报告顺序）')
    expect(wrapper.text()).toContain('S/C:-52140+52141')
    expect(wrapper.text()).toContain('#11001-52140+52141.pdf')
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#rename-download-blockers').text()).toContain('请先勾选复核确认')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.find('#rename-download-blockers').exists()).toBe(false)
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await flushPromises()
    expect(api.executePdfRename).toHaveBeenCalledWith(expect.any(Array), 'buzzbee-inspection', 'review-1', true, 'huaxing', expect.any(AbortSignal), [])
    expect(download).toHaveBeenCalledOnce()
  })

  it('requires a new review after re-recognition and blocks dropped files while busy', async () => {
    const wrapper = await setup()
    let finish!: (value: PdfRenamePreviewResult) => void
    api.previewPdfRename.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await button(wrapper, '生成改名预览').trigger('click')
    await wrapper.get('section[aria-labelledby="batch-upload-title"]').trigger('drop', {
      dataTransfer: { files: [new File(['%PDF-other'], 'other.pdf')] },
    })
    expect(wrapper.text()).toContain('已加入 1 份 PDF')
    finish(structuredClone(result))
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeUndefined()
    await button(wrapper, '重新识别预览').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[type="checkbox"]').element.checked).toBe(false)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    await wrapper.get('select').setValue('')
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('explains the blocking file and error beside download even when review is checked', async () => {
    const failed = structuredClone(result)
    failed.summary = { total: 2, ready: 0, review: 1, error: 1 }
    failed.items.push({ source_file_name: '#11011-52136+52137.pdf', target_file_name: '',
      interval_name: '', status: 'ERROR', fields: [],
      issues: [{ code: 'PDF_RENAME_INTERVAL_INVALID', message: '未识别到唯一的 5 位货号。' }] })
    api.previewPdfRename.mockResolvedValueOnce(failed)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    const blockers = wrapper.get('aside #rename-download-blockers')
    expect(blockers.text()).toContain('仍有 1 份文件存在错误，暂不能下载')
    expect(blockers.text()).toContain('#11011-52136+52137.pdf')
    expect(blockers.text()).toContain('未识别到唯一的 5 位货号。')
    expect(blockers.text()).toContain('勾选复核不会跳过错误')
    expect(button(wrapper, '确认并下载 ZIP').attributes('aria-describedby')).toBe('rename-download-blockers')
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    expect(api.executePdfRename).not.toHaveBeenCalled()
    await button(wrapper, '重新识别预览').trigger('click')
    await flushPromises()
    expect(wrapper.get('#rename-download-blockers').text()).toContain('请先勾选复核确认')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.find('#rename-download-blockers').exists()).toBe(false)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeUndefined()
  })

  it('clears files, preview and review when changing factory and hides foreign rules', async () => {
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.setProps({ factoryId: 'huadeng', contextLabel: '华登厂区' })
    await flushPromises()
    expect(api.getPdfRenameRules).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toBe('')
    expect(wrapper.text()).not.toContain('BuzzBee')
    expect(wrapper.text()).not.toContain('scan.pdf')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    await wrapper.setProps({ factoryId: 'huaxing', contextLabel: '华兴厂区' })
    await flushPromises()
    expect(wrapper.get('select').element.value).toBe('buzzbee-inspection')
    expect(wrapper.text()).not.toContain('scan.pdf')
  })

  it('ignores an old factory preview arriving after a factory switch', async () => {
    const wrapper = await setup()
    let finish!: (value: PdfRenamePreviewResult) => void
    api.previewPdfRename.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await button(wrapper, '生成改名预览').trigger('click')
    const signal = api.previewPdfRename.mock.calls[0]?.[3] as AbortSignal
    await wrapper.setProps({ factoryId: 'huadeng' })
    await flushPromises()
    expect(signal.aborted).toBe(true)
    finish(structuredClone(result))
    await flushPromises()
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('BuzzBee')
  })

  it('does not download an old factory execution result after switching factory', async () => {
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    let finish!: (value: unknown) => void
    api.executePdfRename.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await wrapper.setProps({ factoryId: 'huadeng' })
    finish({ blob: new Blob(['zip']), fileName: 'old.zip', fileCount: 1 })
    await flushPromises()
    expect(download).not.toHaveBeenCalled()
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('ignores a late catalog response from an earlier factory', async () => {
    const wrapper = await setup()
    let finish!: (value: unknown) => void
    api.getPdfRenameRules.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await wrapper.setProps({ factoryId: 'huadeng' })
    await wrapper.setProps({ factoryId: 'huaxing' })
    await wrapper.setProps({ factoryId: 'huadeng' })
    await wrapper.setProps({ factoryId: 'huaxing' })
    await flushPromises()
    finish({ rules: [], limits: { max_files: 50, max_batch_bytes: 200000000, max_file_bytes: 20000000 } })
    await flushPromises()
    expect(wrapper.get('select').element.value).toBe('buzzbee-inspection')
    expect(wrapper.text()).not.toContain('当前厂区暂无可用改名规则')
  })

  it('requires per-file confirmation, applies a manual preview and sends the same overrides for ZIP', async () => {
    const failed = structuredClone(result)
    failed.items[0]!.status = 'ERROR'
    failed.items[0]!.target_file_name = ''
    failed.items[0]!.issues = [{ code: 'PDF_RENAME_INTERVAL_INVALID', message: '货号模糊。' }]
    failed.summary = { total: 1, ready: 0, review: 0, error: 1 }
    const corrected = structuredClone(result)
    corrected.items[0]!.manual_override = true
    api.previewPdfRename.mockResolvedValueOnce(failed).mockResolvedValueOnce(corrected)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    await wrapper.get('input[aria-label="人工文件名 scan.pdf"]').setValue('#11001-52140+52141.pdf')
    expect(wrapper.get('#rename-download-blockers').text()).toContain('请逐份勾选')
    expect(button(wrapper, '应用人工改名').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="确认人工改名 scan.pdf"]').setValue(true)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    await button(wrapper, '应用人工改名').trigger('click')
    await flushPromises()
    const overrides = [{ source_index: 0, target_file_name: '#11001-52140+52141.pdf', confirmed: true }]
    expect(api.previewPdfRename).toHaveBeenLastCalledWith(expect.any(Array), 'buzzbee-inspection', 'huaxing', expect.any(AbortSignal), overrides)
    expect(wrapper.text()).toContain('人工改名 · 待最终复核')
    await wrapper.get('aside input[type="checkbox"]').setValue(true)
    await button(wrapper, '确认并下载 ZIP').trigger('click')
    await flushPromises()
    expect(api.executePdfRename).toHaveBeenLastCalledWith(expect.any(Array), 'buzzbee-inspection', 'review-1', true, 'huaxing', expect.any(AbortSignal), overrides)
    await wrapper.get('input[aria-label="人工文件名 scan.pdf"]').setValue('#11001-99999.pdf')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="确认人工改名 scan.pdf"]').element.checked).toBe(false)
    expect(button(wrapper, '确认并下载 ZIP').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ factoryId: 'huadeng' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('#11001-99999')
  })

  it('does not offer manual release for structural PDF errors', async () => {
    const failed = structuredClone(result)
    failed.items[0]!.status = 'ERROR'
    failed.items[0]!.manual_override_allowed = false
    failed.summary = { total: 1, ready: 0, review: 0, error: 1 }
    api.previewPdfRename.mockResolvedValueOnce(failed)
    const wrapper = await setup()
    await button(wrapper, '生成改名预览').trigger('click')
    await flushPromises()
    expect(wrapper.find('input[aria-label="人工文件名 scan.pdf"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('此异常不能人工放行')
  })
})
