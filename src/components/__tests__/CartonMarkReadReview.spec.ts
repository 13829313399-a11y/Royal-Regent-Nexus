import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CartonMarkReadReview from '../CartonMarkReadReview.vue'
import type { MarkReadResult, MarkReviewEdits } from '@/api/cartonSupplierPortal'

const fixture: MarkReadResult = {
  payload: 'signed-body', signature: 'signature', mode: 'ai', source_cells: 12, paper: 'A3', orientation: 'landscape', warnings: [],
  records: [{ panels: [{ face: 'front', copies: 2, fields: [
    { id: 'r0p0f0', label: 'PO', value: 'PO-DEMO', sources: ['SM!B2'], locked: true, placeholder: false },
    { id: 'r0p0f1', label: '数量', value: '6 PCS', sources: ['SM!B3'], locked: false, placeholder: false },
  ], barcodes: [{ value: '4006381333931', kind: 'EAN13', width_mm: 70, height_mm: 35, frame: 'none' }] }] }],
  notes: [{ id: 'N1', location: 'SM!H3', text: '实际重量待填写', status: 'needs_confirmation' }], images: [],
  unselected_cells: [{ id: 'E8', location: 'SM!C7', text: 'MADE IN CHINA', printable: true }, { id: 'E9', location: '参考!A1', text: 'OLD EXAMPLE', printable: false }],
}
function submit(wrapper: ReturnType<typeof mount>) { return wrapper.findAll('button').find(b => b.text() === '更新预览（不重新读稿）')!.trigger('click') }

describe('source-backed carton mark review', () => {
  it('can decline a source-linked exception without changing the reusable template', async () => {
    const review: MarkReadResult = { ...fixture, customer_template: { id:'zuru-front-side-v1',name:'客户模板',version:1,reference_sha256:'reference' }, order_changes:[{record:0,face:'front',summary:'正唛居中',note_ids:['N1']}] }
    const wrapper=mount(CartonMarkReadReview,{props:{review,busy:false}})
    expect(wrapper.text()).toContain('不会覆盖通用模板')
    await wrapper.get('[aria-label="采用本单修改 1"]').setValue(false)
    await submit(wrapper)
    expect(wrapper.emitted('render')![0]![0]).toMatchObject({ignored_changes:[0],edits:{}})
    wrapper.unmount()
  })
  it('keeps PO identity fixed and submits only explicit corrections and reviewed notes', async () => {
    const wrapper = mount(CartonMarkReadReview, { props: { review: fixture, busy: false } })
    expect(wrapper.get('[aria-label="第1组正唛 PO"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="第1组正唛 数量"]').setValue('12 PCS')
    await wrapper.get('[aria-label="已核对 SM!H3"]').setValue(true)
    await submit(wrapper)
    expect(wrapper.emitted('render')![0]![0]).toEqual({ edits: { r0p0f1: '12 PCS' }, reviewed_notes: ['N1'], paper: 'A3', orientation: 'landscape', additions: [], omissions: [], graphics: [], include_sources: false })
    expect(wrapper.text()).toContain('原文：6 PCS')
    wrapper.unmount()
  })
  it('adds native source text or a manual field to a selected face without treating reference text as current data', async () => {
    const wrapper = mount(CartonMarkReadReview, { props: { review: fixture, busy: false } })
    const options = wrapper.get('[aria-label="待添加的原稿字段"]').text()
    expect(options).toContain('MADE IN CHINA'); expect(options).not.toContain('OLD EXAMPLE')
    await wrapper.get('[aria-label="补充字段的箱面"]').setValue('0:side')
    await wrapper.get('[aria-label="待添加的原稿字段"]').setValue('E8')
    await wrapper.findAll('button').find(b => b.text() === '添加原文字段')!.trigger('click')
    await wrapper.get('[aria-label="新增字段名称"]').setValue('NW')
    await wrapper.get('[aria-label="新增字段内容"]').setValue('2.5 KGS')
    await wrapper.findAll('button').find(b => b.text() === '添加本次补充')!.trigger('click')
    await submit(wrapper)
    const result = wrapper.emitted('render')![0]![0] as MarkReviewEdits
    expect(result.additions).toEqual([{ record: 0, face: 'side', source_id: 'E8' }, { record: 0, face: 'side', label: 'NW', value: '2.5 KGS' }])
    wrapper.unmount()
  })
  it('shows a native arrangement needing mapping honestly and disables all mutations while rendering', async () => {
    const wrapper = mount(CartonMarkReadReview, { props: { review: { ...fixture, mode: 'needs_mapping' }, busy: true } })
    expect(wrapper.text()).toContain('这不算 AI 自动排版成功')
    expect(wrapper.findAll('button').every(b => b.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.findAll('textarea').every(b => b.attributes('disabled') !== undefined)).toBe(true)
    wrapper.unmount()
  })
  it('keeps complete records collapsed and exposes only source-linked missing fields by default', async () => {
    const pending = { ...fixture, issues: [{ kind: 'missing_value', message: '请补充实际数量', field_ids: ['r0p0f1'], sources: ['SM!B3'] }] }
    const wrapper = mount(CartonMarkReadReview, { props: { review: pending, busy: false } })
    expect(wrapper.get('[aria-label="高级调整与完整原稿记录"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[aria-label="需要确认的项目"]').text()).toContain('请补充实际数量')
    expect(wrapper.find('[aria-label="已核对 SM!H3"]').element.closest('details[open]')).toBeNull()
    await wrapper.get('[aria-label="补充 r0p0f1 数量"]').setValue('12 PCS'); await submit(wrapper)
    const sent = wrapper.emitted('render')![0]![0] as MarkReviewEdits
    expect(sent.edits).toEqual({ r0p0f1: '12 PCS' }); expect(sent.reviewed_notes).toEqual([])
    await wrapper.setProps({ applied: sent })
    expect(wrapper.find('[aria-label="需要确认的项目"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(b => b.text()==='更新预览（不重新读稿）')).toBe(false)
    wrapper.unmount()
  })
})
