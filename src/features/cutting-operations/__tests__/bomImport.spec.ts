import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CuttingBomImport from '../CuttingBomImport.vue'
import type { BomPreview } from '../bomImportApi'

const api = vi.hoisted(() => ({ preview: vi.fn(), confirm: vi.fn(), recover: vi.fn(), template: vi.fn() }))
vi.mock('../bomImportApi', () => ({ bomImportApi: api }))

const source = { file_name: '工程.xlsx', file_sha256: 'a'.repeat(64) }
const material = { material_id: 'cloth', material_version: 3, part_codes: ['01'], quantity_per_set: '0.125001',
  unit: '米', stage: '裁剪', required_for_cutting: true, note: '' }
const data = { name: '蓝色套装', item_no: '00012', style: '测试款', color: '蓝', source_reference: 'ENG-V1',
  parts: [{ code: '01', name: '左片', pieces_per_set: 2 }], requirements: [material] }
const preview: BomPreview = { ...source, fingerprint: 'b'.repeat(64), issues: [],
  candidate: { code: 'B-001', existing_id: null, expected_version: 0, data,
    material_rows: [{ ...material, row: 2, material_code: 'M001', material_name: '蓝布' }] } }
const response = { ...source, record: { id: 'bom-1', code: 'B-001', kind: 'bom', status: 'draft', version: 1, data } }
beforeEach(() => {
  vi.resetAllMocks()
  api.preview.mockResolvedValue(preview)
  api.confirm.mockResolvedValue(response)
})
function button(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll('button').find(item => item.text() === label)!
}
async function readWorkbook() {
  const wrapper = mount(CuttingBomImport)
  await button(wrapper, '导入工程 BOM').trigger('click')
  const input = wrapper.get('input[type=file]')
  const file = new File(['test'], source.file_name)
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await button(wrapper, '预览并校验').trigger('click')
  await flushPromises()
  return { wrapper, file }
}
async function confirm(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[name=cutting_bom_import_reason]').setValue('工程合成验收')
  await wrapper.get('input[type=checkbox]').setValue(true)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

it('shows row-specific validation failures and offers no draft confirmation', async () => {
  api.preview.mockResolvedValue({ ...preview, candidate: null, fingerprint: null,
    issues: [{ sheet: '物料用量', row: 2, message: '单位不一致' }] })
  const { wrapper } = await readWorkbook()
  expect(wrapper.text()).toContain('物料用量 · 第 2 行：单位不一致')
  expect(button(wrapper, '确认生成 BOM 草稿')).toBeUndefined()
  expect(api.confirm).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('previews the pinned material and confirms only a draft after acknowledgement', async () => {
  const { wrapper, file } = await readWorkbook()
  expect(wrapper.text()).toContain('M001 · 蓝布 · V3')
  expect(wrapper.text()).toContain('0.125001 米')
  expect(button(wrapper, '确认生成 BOM 草稿').attributes('disabled')).toBeDefined()
  await confirm(wrapper)
  expect(api.confirm).toHaveBeenCalledWith(file, expect.objectContaining({ expected_version: 0, fingerprint: preview.fingerprint }))
  expect(wrapper.emitted('imported')).toEqual([[response.record]])
  expect(wrapper.text()).toContain('已生成 BOM 草稿 B-001 V1')
  wrapper.unmount()
})

it('keeps the same operation and file for unknown outcomes until recovery', async () => {
  api.confirm.mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce({ response: { status: 409 } })
  api.recover.mockResolvedValue({ state: 'committed', result: response })
  const { wrapper, file } = await readWorkbook()
  await confirm(wrapper)
  const command = api.confirm.mock.calls[0][1]
  expect(wrapper.get('input[type=file]').attributes('disabled')).toBeDefined()
  await button(wrapper, '重试原导入').trigger('click')
  await flushPromises()
  expect(api.confirm).toHaveBeenLastCalledWith(file, command)
  await button(wrapper, '核对原导入结果').trigger('click')
  await flushPromises()
  expect(api.recover).toHaveBeenCalledWith(command)
  expect(wrapper.emitted('imported')).toEqual([[response.record]])
  wrapper.unmount()
})
