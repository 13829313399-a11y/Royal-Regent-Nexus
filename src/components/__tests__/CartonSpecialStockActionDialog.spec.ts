import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonSpecialStockActionDialog.vue'
import { cartonSpecialStockActionsApi as api, type SpecialStockAction, type SpecialStockPreview, type SpecialStockResult } from '@/api/cartonSpecialStockActions'

const auth = reactive({ currentUser: { id: 'warehouse' }, authorizationVersion: 1, permitted: true })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({
  get currentUser() { return auth.currentUser }, get authorizationVersion() { return auth.authorizationVersion },
  can: () => auth.permitted,
}) }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (error: Error) => error.message }))
vi.mock('@/api/cartonSpecialStockActions', () => ({ cartonSpecialStockActionsApi: { preview: vi.fn(), submit: vi.fn(), undo: vi.fn() } }))
const source = { id: 'SP1', request_no: 'SP-001', revision: 5, status: 'COMPLETED' }
const preview = (): SpecialStockPreview => ({ source_request: source, source_fingerprint: 'stock-basis-1', can_return: true, can_replenish: true, blockers: [], replacement: null,
  lines: [{ receipt_line_id: 'RL1', movement_id: 'IM1', location_id: 'BIN1', location_label: '一仓A', receipt_no: 'RC1', request_line_id: 'SL1', item_no: 'BOX', packaging_type: '外箱', paper_quality: 'A33', specification: '20*10*5', dimension_unit: 'cm', unit: '个', currency: 'CNY', received_quantity: '10', safe_quantity: '8', inventory_unit_price: '2', inventory_amount: '20', blockers: [] }] })
const response = (action: SpecialStockAction = 'RETURN'): SpecialStockResult => ({ action, source_request: { ...source, revision: 6 }, movement_ids: ['OUT1'], replenishment_request: action === 'REPLENISH' ? { id: 'B1', request_no: 'SP-001-B01', revision: 1, status: 'SENT' } : null })
function open(action: SpecialStockAction = 'RETURN') {
  return mount(Component, { props: { factoryId: 'huaxing', requestId: 'SP1', requestNo: 'SP-001', action, viewerKey: 'viewer' }, global: { stubs: {
    DialogRoot: { template: '<div><slot /></div>' }, DialogOverlay: true, DialogContent: { template: '<section role="dialog"><slot /></section>' },
    DialogTitle: { template: '<h2><slot /></h2>' }, DialogDescription: { template: '<p><slot /></p>' },
  } } })
}
const button = (w: ReturnType<typeof open>, text: string) => w.findAll('button').find(b => b.text() === text)!
async function fill(w: ReturnType<typeof open>, qty = '3') {
  await w.get('[aria-label="RC1 外箱 一仓A 本次数量"]').setValue(qty)
  await w.get('[aria-label="办理原因"]').setValue('核实实际退回')
}
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); auth.currentUser = { id: 'warehouse' }; auth.authorizationVersion = 1; auth.permitted = true
  vi.mocked(api.preview).mockResolvedValue(preview()); vi.mocked(api.submit).mockResolvedValue(response()); vi.mocked(api.undo).mockResolvedValue(response('UNDO'))
})
afterEach(() => vi.restoreAllMocks())

describe('样板杂单库存动作', () => {
  it('opens read-only and submits exact source/bin, quantity and basis only after confirmation', async () => {
    const w = open(); await flushPromises()
    expect(api.submit).not.toHaveBeenCalled(); expect(api.undo).not.toHaveBeenCalled()
    expect(w.text()).toContain('原需求和已收记录保留')
    await fill(w); await w.get('form').trigger('submit'); await flushPromises()
    expect(api.submit).toHaveBeenCalledWith('SP1', expect.objectContaining({ factory_id: 'huaxing', expected_revision: 5, source_fingerprint: 'stock-basis-1', action: 'RETURN', reason: '核实实际退回', return_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), lines: [{ receipt_line_id: 'RL1', movement_id: 'IM1', location_id: 'BIN1', quantity: '3' }] }), expect.any(AbortSignal))
    expect(w.emitted('changed')).toHaveLength(1); expect(w.text()).toContain('退货签收与退款'); expect(localStorage.length).toBe(0); w.unmount()
  })
  it.each(['9', '-1', '1e2', '0.00001'])('rejects invalid or excessive quantity %s without writing', async qty => {
    const w = open(); await flushPromises(); await fill(w, qty); await w.get('form').trigger('submit'); await flushPromises()
    expect(api.submit).not.toHaveBeenCalled(); expect(w.get('[role="alert"]').text()).toContain('核对数量'); w.unmount()
  })
  it('requires responsibility and blocks supplier-free replacement when original cost is unknown', async () => {
    const data = preview(); data.lines[0]!.inventory_unit_price = null; vi.mocked(api.preview).mockResolvedValue(data)
    const w = open('REPLENISH'); await flushPromises(); await fill(w)
    await w.get('form').trigger('submit'); expect(api.submit).not.toHaveBeenCalled(); expect(w.text()).toContain('请选择补单责任方')
    await w.get('[aria-label="补单责任方"]').setValue('SUPPLIER'); await w.get('form').trigger('submit')
    expect(api.submit).not.toHaveBeenCalled(); expect(w.get<HTMLInputElement>('[aria-label="RC1 外箱 一仓A 本次数量"]').element.disabled).toBe(true)
    await w.get('[aria-label="补单责任方"]').setValue('OWN'); vi.mocked(api.submit).mockResolvedValue(response('REPLENISH'))
    await w.get('form').trigger('submit'); await flushPromises()
    expect(api.submit).toHaveBeenCalledWith('SP1', expect.objectContaining({ action: 'REPLENISH', responsibility: 'OWN', required_date: expect.any(String) }), expect.any(AbortSignal))
    expect(w.text()).toContain('SP-001-B01'); w.unmount()
  })
  it('retains an unknown result across closing/reopening and replays the exact original request after stock changes', async () => {
    vi.mocked(api.submit).mockRejectedValueOnce(new Error('网络中断'))
    const first = open(); await flushPromises(); await fill(first); await first.get('form').trigger('submit'); await flushPromises()
    const body = vi.mocked(api.submit).mock.calls[0]![1]
    expect(first.text()).toContain('结果尚未确认'); expect(localStorage.length).toBe(1); first.unmount()
    vi.mocked(api.preview).mockResolvedValue({ ...preview(), can_return: false, lines: [], source_fingerprint: 'new-basis', source_request: { ...source, revision: 6 } })
    const second = open(); await flushPromises()
    expect(second.get<HTMLInputElement>('[aria-label="RC1 外箱 一仓A 本次数量"]').element.value).toBe('3')
    expect(second.get<HTMLInputElement>('[aria-label="RC1 外箱 一仓A 本次数量"]').element.disabled).toBe(true)
    expect(button(second, '核对原结果 / 重试').attributes('disabled')).toBeUndefined()
    await second.get('form').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.submit).mock.calls[1]![1]).toEqual(body); expect(second.emitted('changed')).toHaveLength(1); second.unmount()
  })
  it('clears definite validation failure but keeps request-ID conflicts frozen for investigation', async () => {
    vi.mocked(api.submit).mockRejectedValueOnce(Object.assign(new Error('库存数量已变化'), { response: { status: 409 } }))
    const w = open(); await flushPromises(); await fill(w); await w.get('form').trigger('submit'); await flushPromises()
    expect(localStorage.length).toBe(0); expect(w.text()).toContain('重新核对可办理数量')
    await button(w, '重新核对来源').trigger('click'); await flushPromises(); await fill(w)
    vi.mocked(api.submit).mockRejectedValueOnce(Object.assign(new Error('提交标识已用于其他内容'), { response: { status: 409 } }))
    await w.get('form').trigger('submit'); await flushPromises(); expect(localStorage.length).toBe(1); expect(w.text()).toContain('核对原结果 / 重试'); w.unmount()
  })
  it.each([404, 409, 422])('preserves an already-unknown request through authorization refresh and later %s', async status => {
    vi.mocked(api.submit).mockRejectedValueOnce(new Error('提交结果不明'))
    const w = open(); await flushPromises(); await fill(w); await w.get('form').trigger('submit'); await flushPromises()
    const body = vi.mocked(api.submit).mock.calls[0]![1]
    auth.authorizationVersion++; await flushPromises()
    expect(localStorage.length).toBe(1); expect(w.text()).toContain('本次内容已冻结')
    vi.mocked(api.submit).mockRejectedValueOnce(Object.assign(new Error('来源暂不可访问'), { response: { status } }))
    await w.get('form').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.submit).mock.calls[1]![1]).toEqual(body); expect(localStorage.length).toBe(1)
    if (status === 404) { expect(w.text()).not.toContain('RC1'); expect(button(w, '核对原结果 / 重试').attributes('disabled')).toBeDefined() }
    w.unmount()
  })
  it('does not display persisted private source data or replay until current source access succeeds', async () => {
    vi.mocked(api.submit).mockRejectedValueOnce(new Error('未知结果'))
    const first = open(); await flushPromises(); await fill(first); await first.get('form').trigger('submit'); await flushPromises(); first.unmount()
    vi.mocked(api.preview).mockRejectedValueOnce(Object.assign(new Error('客户责任权限已变化'), { response: { status: 403 } }))
    const second = open(); await flushPromises(); expect(second.text()).not.toContain('RC1'); expect(localStorage.length).toBe(1)
    expect(button(second, '核对原结果 / 重试').attributes('disabled')).toBeDefined()
    await second.get('form').trigger('submit'); expect(api.submit).toHaveBeenCalledTimes(1)
    await button(second, '重新核对来源').trigger('click'); await flushPromises(); expect(second.text()).toContain('RC1')
    await second.get('form').trigger('submit'); await flushPromises(); expect(api.submit).toHaveBeenCalledTimes(2); second.unmount()
  })
  it('ignores a previous factory read and does not carry private quantities across scope changes', async () => {
    let complete!: (value: SpecialStockPreview) => void
    vi.mocked(api.preview).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const w = open(); await flushPromises()
    vi.mocked(api.preview).mockResolvedValue({ ...preview(), source_request: { ...source, id: 'SP2' }, lines: [] })
    await w.setProps({ factoryId: 'huadeng', requestId: 'SP2', requestNo: 'SP-002' }); await flushPromises()
    complete(preview()); await flushPromises()
    expect(w.text()).not.toContain('RC1'); expect(w.text()).toContain('SP-002'); expect(api.submit).not.toHaveBeenCalled(); w.unmount()
  })
  it('revoking permission discards private UI and ignores an old successful write response', async () => {
    let complete!: (value: SpecialStockResult) => void
    vi.mocked(api.submit).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const w = open(); await flushPromises(); await fill(w); await w.get('form').trigger('submit'); await flushPromises()
    auth.permitted = false; await flushPromises(); complete(response()); await flushPromises()
    expect(w.text()).toContain('此操作需要本厂订单和库存权限'); expect(w.text()).not.toContain('RC1'); expect(w.emitted('changed')).toBeUndefined(); w.unmount()
  })
  it('keeps empty or ambiguous sources blocked rather than treating them as safe stock', async () => {
    vi.mocked(api.preview).mockResolvedValue({ ...preview(), can_return: false, lines: [], blockers: ['原收料没有可验证仓位分摊'] })
    const w = open(); await flushPromises(); expect(w.text()).toContain('没有可验证仓位分摊')
    expect(button(w, '确认实际退货').attributes('disabled')).toBeDefined(); await w.get('form').trigger('submit'); expect(api.submit).not.toHaveBeenCalled(); w.unmount()
  })
  it('uses the dedicated undo endpoint without pretending to create a negative return or append', async () => {
    vi.mocked(api.preview).mockResolvedValue({ ...preview(), lines: [], replacement: { parent_request_id: 'ORIGINAL', parent_request_no: 'SP-000', responsibility: 'SUPPLIER', can_undo: true, blockers: [] } })
    const w = open('UNDO'); await flushPromises(); await w.get('[aria-label="办理原因"]').setValue('换补申请录错'); await w.get('form').trigger('submit'); await flushPromises()
    expect(api.submit).not.toHaveBeenCalled(); expect(api.undo).toHaveBeenCalledWith('SP1', expect.objectContaining({ expected_revision: 5, factory_id: 'huaxing', reason: '换补申请录错' }), expect.any(AbortSignal)); expect(w.text()).toContain('换补出库已冲回'); w.unmount()
  })
  it('does not write if pending request cannot be persisted', async () => {
    const w = open(); await flushPromises(); await fill(w)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage denied') })
    await w.get('form').trigger('submit'); await flushPromises(); expect(api.submit).not.toHaveBeenCalled(); expect(w.text()).toContain('尚未提交'); w.unmount()
  })
})
