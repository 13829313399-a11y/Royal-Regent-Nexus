// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { qcInspectionApi, type QcScheduleImport, type QcWorkspace } from '@/api/qcInspection'
import { qcInspectionWorkspaceKey, type QcInspectionWorkspaceContext } from '../context'
import QcImportPanel from '../QcImportPanel.vue'

vi.mock('@/api/qcInspection', () => ({ qcInspectionApi: { getScheduleImport: vi.fn(), confirmScheduleImport: vi.fn() }, validateQcScheduleImportFile: () => '' }))
const batch = { id: 'batch', revision: 1, week_key: '2026-W38', source_file_name: '排期.xlsx', rows: Array.from({ length: 33 }, (_, index) => ({
  id: `row-${index}`, source_row_no: index + 4, customer_name: index < 31 ? 'WMC' : 'WMU',
  source_sheet_name: '正单评审表', match_status: index === 32 ? 'INVALID' : 'NEW',
  decision_status: 'PENDING', changes: [], candidate_order_ids: [], validation_errors: index === 32 ? ['PO不能为空'] : [],
})) } as unknown as QcScheduleImport
function context(writable = true): QcInspectionWorkspaceContext {
  const allowed = computed(() => writable)
  return { factoryId: computed(() => 'huaxing'), factoryName: computed(() => '华兴'), weekKey: computed(() => '2026-W38'),
    workspace: ref({ imports: [batch] } as QcWorkspace), state: ref('ready'), errorMessage: ref(''),
    canScheduleWrite: allowed, canOrderWrite: allowed, canResultWrite: allowed, canProblemWrite: allowed,
    canReportExport: allowed, canGroupSummary: allowed, canFactorySummary: allowed, refresh: vi.fn(), setWeek: vi.fn() }
}
const render = (writable = true) => mount(QcImportPanel, { global: { provide: { [qcInspectionWorkspaceKey as symbol]: context(writable) } } })
beforeEach(() => { vi.clearAllMocks(); vi.mocked(qcInspectionApi.getScheduleImport).mockResolvedValue(structuredClone(batch)) })
describe('QC bulk import interaction', () => {
  it('selects across pages, excludes errors, and confirms only checked rows', async () => {
    const wrapper = render()
    await wrapper.find('select').setValue('batch'); await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(30)
    await wrapper.find('select').setValue('batch')
    await wrapper.find('input[aria-label="全选当前筛选下可导入的订单"]').setValue(true)
    expect(wrapper.text()).toContain('已选 32 条：新增 32 条')
    await wrapper.find('input[aria-label="选择第 4 行"]').setValue(false)
    const response = structuredClone(batch)
    response.revision = 2
    response.rows.forEach(row => { if (row.id !== 'row-0' && row.id !== 'row-32') row.decision_status = 'CREATE' })
    vi.mocked(qcInspectionApi.confirmScheduleImport).mockResolvedValue(response)
    await wrapper.findAll('button').find(button => button.text().includes('确认导入所选'))!.trigger('click')
    await flushPromises()
    const call = vi.mocked(qcInspectionApi.confirmScheduleImport).mock.calls[0]!
    expect(call.slice(0, 3)).toEqual(['batch', 'huaxing', 1])
    expect(call[3]).toHaveLength(31)
    expect(call[3].map(row => row.row_id)).not.toContain('row-0')
    expect(call[3].map(row => row.row_id)).not.toContain('row-32')
    expect(wrapper.text()).toContain('剩余 2 条待确认')
  })
  it('retains selection through filters while allowing a filtered select-all', async () => {
    const wrapper = render()
    await wrapper.find('select').setValue('batch'); await flushPromises()
    await wrapper.find('input[aria-label="选择第 4 行"]').setValue(true)
    await wrapper.findAll('select')[1]!.setValue('WMU')
    await wrapper.find('input[aria-label="全选当前筛选下可导入的订单"]').setValue(true)
    expect(wrapper.text()).toContain('已选 2 条：新增 2 条')
    expect(wrapper.find('input[aria-label="选择第 36 行"]').attributes('disabled')).toBeDefined()
  })
  it('disables selection and writes for a read-only user', async () => {
    const wrapper = render(false)
    await wrapper.find('select').setValue('batch'); await flushPromises()
    expect(wrapper.find('input[aria-label="全选当前筛选下可导入的订单"]').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').find(button => button.text().includes('确认导入所选'))!.attributes('disabled')).toBeDefined()
    expect(qcInspectionApi.confirmScheduleImport).not.toHaveBeenCalled()
  })

  it('allows an explicit skip for an invalid row without importing it', async () => {
    const wrapper = render()
    await wrapper.find('select').setValue('batch'); await flushPromises()
    await wrapper.findAll('select')[1]!.setValue('WMU')
    await wrapper.find('select[aria-label="第 36 行处理方式"]').setValue('SKIP')
    await wrapper.find('input[aria-label="选择第 36 行"]').setValue(true)
    vi.mocked(qcInspectionApi.confirmScheduleImport).mockResolvedValue(batch)
    await wrapper.findAll('button').find(button => button.text().includes('确认导入所选'))!.trigger('click'); await flushPromises()
    expect(vi.mocked(qcInspectionApi.confirmScheduleImport).mock.calls[0]![3]).toEqual([{ row_id: 'row-32', action: 'SKIP', target_order_id: undefined }])
  })

  it('chunks more than 1000 decisions and reloads partial progress after a failure', async () => {
    const large = { ...batch, rows: Array.from({ length: 1001 }, (_, index) => ({ ...batch.rows[0]!, id: `large-${index}`, source_row_no: index + 4 })) }
    const partial = { ...large, revision: 2, rows: large.rows.map((row, index) => ({ ...row, decision_status: index < 1000 ? 'CREATE' : 'PENDING' })) }
    vi.mocked(qcInspectionApi.getScheduleImport).mockResolvedValueOnce(large).mockResolvedValueOnce(partial)
    vi.mocked(qcInspectionApi.confirmScheduleImport).mockResolvedValueOnce(partial).mockRejectedValueOnce(new Error('network interrupted'))
    const wrapper = render()
    await wrapper.find('select').setValue('batch'); await flushPromises()
    await wrapper.find('input[aria-label="全选当前筛选下可导入的订单"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text().includes('确认导入所选'))!.trigger('click'); await flushPromises()
    const calls = vi.mocked(qcInspectionApi.confirmScheduleImport).mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[0]![2]).toBe(1); expect(calls[0]![3]).toHaveLength(1000)
    expect(calls[1]![2]).toBe(2); expect(calls[1]![3]).toHaveLength(1)
    expect(wrapper.text()).toContain('本次已确认处理 1000 条')
    expect(wrapper.text()).toContain('待确认 1 条')
    expect(wrapper.text()).toContain('已选 0 条')
  })
})
