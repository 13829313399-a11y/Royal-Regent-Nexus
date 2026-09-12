import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PdfRenamePreviewResult, PdfRenameRuleDefinition } from '@/api/pdfRename'
import PdfBatchRenameWorkspace from './PdfBatchRenameWorkspace.vue'

const api = vi.hoisted(() => ({ getPdfRenameRules: vi.fn(), previewPdfRename: vi.fn(), executePdfRename: vi.fn() }))
const download = vi.hoisted(() => vi.fn())
vi.mock('@/api/pdfRename', () => ({ pdfRenameApi: api, PdfRenameApiError: class extends Error {} }))
vi.mock('./pdfRenameUtils', async (importOriginal) => ({ ...await importOriginal<typeof import('./pdfRenameUtils')>(), downloadToolBlob: download }))

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

beforeEach(() => {
  vi.clearAllMocks()
  api.getPdfRenameRules.mockResolvedValue({ rules: [rule], limits: { max_files: 50, max_batch_bytes: 200 * 1024 * 1024, max_file_bytes: 20 * 1024 * 1024 } })
  api.previewPdfRename.mockResolvedValue(structuredClone(result))
  api.executePdfRename.mockResolvedValue({ blob: new Blob(['zip']), fileName: 'results.zip', fileCount: 1 })
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

async function setup() {
  const wrapper = mount(PdfBatchRenameWorkspace, { props: { contextLabel: '华兴厂区', factoryId: 'huaxing' } })
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

describe('BuzzBee batch rename review workflow', () => {
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
