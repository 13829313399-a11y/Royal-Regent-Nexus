import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonPriceCorrections.vue'
import { cartonPriceCorrectionsApi as api, pendingPriceCorrection, type PriceCorrectionDetail } from '@/api/cartonPriceCorrections'
import { correctionImpact, correctionRow, correctionWorkspace } from './cartonPriceCorrectionsFixture'
const mocks = vi.hoisted(() => ({ can: vi.fn((_code: string, _factory?: string, _dept?: string) => true) }))
const identity = reactive({ currentUser: { id: 'warehouse' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: mocks.can, get currentUser() { return identity.currentUser }, get authorizationVersion() { return identity.authorizationVersion } }) }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (cause: Error) => cause.message }))
vi.mock('@/api/cartonPriceCorrections', () => ({ cartonPriceCorrectionsApi: { workspace: vi.fn(), detail: vi.fn(), preview: vi.fn(), act: vi.fn() }, pendingPriceCorrection: vi.fn() }))
const props = { factoryId: 'huaxing', internal: true, viewerKey: 'operator-context' }
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(row => row.text() === text)!
function warehouse() { mocks.can.mockImplementation(code => !code.endsWith(':closing_manage') && !code.endsWith(':order_adjust') && !code.startsWith('carton_supplier:')) }
async function opened(overrides = {}) { const w = mount(Component, { props: { ...props, receiptLineId: 'LINE1', ...overrides } }); await flushPromises(); return w }
async function proposal(w: ReturnType<typeof mount>, amount = '3.123456') { await button(w, '提出单价更正').trigger('click'); await w.get('[aria-label="更正提议新单价"]').setValue(amount); await w.get('[aria-label="更正价格凭证号"]').setValue('报价凭证-001'); await w.get('[aria-label="更正价格凭证日期"]').setValue('2026-10-20'); await w.get('[aria-label="单价更正处理依据"]').setValue('核对原报价录入错误') }
beforeEach(() => { vi.resetAllMocks(); identity.currentUser = { id: 'warehouse' }; identity.authorizationVersion = 1; mocks.can.mockReturnValue(true); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-21T03:00:00Z')); vi.mocked(api.workspace).mockResolvedValue(correctionWorkspace()); vi.mocked(api.detail).mockResolvedValue(correctionRow()); vi.mocked(api.preview).mockResolvedValue({ ...correctionRow(), impact: correctionImpact() }); vi.mocked(api.act).mockResolvedValue(correctionRow({ status: 'APPLIED', revision: 3, current_unit_price: '3', current_cost_unit_price: '3', allowed_actions: ['PROPOSE'] })); vi.mocked(pendingPriceCorrection).mockReturnValue(null) })
afterEach(() => vi.useRealTimers())
describe('three-role receipt price correction', () => {
  it('lets warehouse propose exact receipt-line decimal evidence while withholding supervisor and supplier actions', async () => {
    warehouse(); const w = await opened(); await proposal(w)
    expect(button(w, '预览成本与账单影响')).toBeUndefined(); expect(button(w, '确认本批新价')).toBeUndefined(); expect(w.find('[aria-label="主管成本与账单预览"]').exists()).toBe(false)
    await w.get('form').trigger('submit'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith(true, 'LINE1', { factory_id: 'huaxing', expected_revision: 2, source_fingerprint: 's'.repeat(64), action: 'PROPOSE', reason: '核对原报价录入错误', proposed_unit_price: '3.123456', free_confirmed: false, document_no: '报价凭证-001', document_date: '2026-10-20' }, expect.any(String), expect.any(AbortSignal))
    expect(api.preview).not.toHaveBeenCalled(); w.unmount()
  })
  it('requires explicit free evidence and retains invalid or rejected inputs for correction', async () => {
    warehouse(); const w = await opened(); await proposal(w, '0'); await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled()
    await w.get('[aria-label="确认更正新价免费"]').setValue(true); vi.mocked(api.act).mockRejectedValueOnce(new Error('原免费批次不可改价'))
    await w.get('form').trigger('submit'); await flushPromises(); expect(api.act).toHaveBeenCalledWith(true, 'LINE1', expect.objectContaining({ proposed_unit_price: '0', free_confirmed: true }), expect.any(String), expect.any(AbortSignal))
    expect(w.get<HTMLInputElement>('[aria-label="更正提议新单价"]').element.value).toBe('0'); expect(w.get('[role="alert"]').text()).toContain('原免费批次不可改价'); w.unmount()
  })
  it('withdraws only the current proposal with a reason and exact source evidence', async () => {
    warehouse(); vi.mocked(api.act).mockResolvedValueOnce(correctionRow({ status: 'WITHDRAWN', revision: 3, allowed_actions: ['PROPOSE'] }))
    const w = await opened(); await button(w, '撤回本次提议').trigger('click'); await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled()
    await w.get('[aria-label="单价更正处理依据"]').setValue('报价依据尚需重新核实'); await w.get('form').trigger('submit'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith(true, 'LINE1', expect.objectContaining({ action: 'WITHDRAW', expected_revision: 2, source_fingerprint: 's'.repeat(64) }), expect.any(String), expect.any(AbortSignal))
    expect(w.get('[aria-label="原价当前价与提议价"]').text()).toContain('历史提议价（已撤回）'); expect(w.text()).toContain('原价'); w.unmount()
  })
  it('shows supplier only published commercial evidence and exact-version confirmation even if an overbroad fixture contains internal data', async () => {
    mocks.can.mockImplementation(code => code.startsWith('carton_supplier:'))
    const row = correctionRow({ raw_unit_price: '987654.4321', current_cost_unit_price: '876543.321', status: 'PENDING_SUPPLIER', allowed_actions: ['SUPPLIER_CONFIRM', 'SUPPLIER_DISPUTE', 'FINAL_CONFIRM', 'PROPOSE'], impact: correctionImpact(), history: [{ id: 'secret', action: 'PROPOSE', actor_name: '仓管', created_at: '2026-10-20', reason: '报价核实', data: { location: '秘密仓位', cost: '内部成本数据' } }] })
    vi.mocked(api.detail).mockResolvedValue(row); const w = await opened({ internal: false, factories: [{ factory_id: 'huaxing' }] })
    expect(w.get('[aria-label="原价当前价与提议价"]').text()).toContain('2.1'); expect(w.text()).not.toMatch(/987654|876543|秘密仓位|内部成本数据|领料-001|当前有效入库成本/)
    expect(button(w, '提出单价更正')).toBeUndefined(); expect(button(w, '预览成本与账单影响')).toBeUndefined()
    await button(w, '确认本批新价').trigger('click'); await w.get('[aria-label="单价更正处理依据"]').setValue('核对该批价格凭证'); await w.get('form').trigger('submit'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith(false, 'LINE1', expect.objectContaining({ action: 'SUPPLIER_CONFIRM', expected_revision: 2, source_fingerprint: row.source_fingerprint }), expect.any(String), expect.any(AbortSignal)); expect(api.preview).not.toHaveBeenCalled(); w.unmount()
  })
  it('prevents supplier readers and internal readers from gaining write actions', async () => {
    mocks.can.mockImplementation(code => code.endsWith(':read')); const w = await opened({ internal: false, factories: [{ factory_id: 'huaxing' }] }); expect(button(w, '确认本批新价')).toBeUndefined(); expect(button(w, '提出单价更正')).toBeUndefined(); w.unmount()
    const reader = await opened(); expect(button(reader, '提出单价更正')).toBeUndefined(); expect(button(reader, '预览成本与账单影响')).toBeUndefined(); reader.unmount()
    mocks.can.mockReturnValue(false); vi.mocked(api.workspace).mockClear(); vi.mocked(api.detail).mockClear(); const denied = await opened(); expect(api.workspace).not.toHaveBeenCalled(); expect(api.detail).not.toHaveBeenCalled(); expect(denied.text()).toContain('没有当前厂区'); denied.unmount()
  })
  it('shows exact cost impact and blocker navigation without automatically unlocking, reopening or changing funds', async () => {
    const blocker = { code: 'ACTIVE_ALLOCATION', message: '原账单SEP-001版本1已核销200，须先解除', kind: 'ALLOCATION' as const, id: 'ALLOC1', period: '2026-09' }
    vi.mocked(api.preview).mockResolvedValue({ ...correctionRow(), impact: correctionImpact({ can_apply: false, blockers: [blocker] }) })
    const w = await opened(); await button(w, '预览成本与账单影响').trigger('click'); await flushPromises()
    expect(w.get('[aria-label="主管成本与账单预览"]').text()).toContain('领料-001'); expect(w.text()).toContain('期末余存成本差 4.000000'); expect(w.text()).toContain('真实付款'); expect(button(w, '主管确认更正生效').attributes('disabled')).toBeDefined()
    await button(w, '去解除原核销').trigger('click'); expect(w.emitted('navigate')?.[0]).toEqual([blocker, 'CNY']); expect(api.act).not.toHaveBeenCalled(); w.unmount()
  })
  it('labels an unknown payable difference explicitly and never exposes that internal impact to supplier', async () => {
    const impact = correctionImpact(); impact.summary.payable_difference = null
    vi.mocked(api.preview).mockResolvedValue({ ...correctionRow({ current_unit_price: null }), impact })
    const w = await opened(); await button(w, '预览成本与账单影响').trigger('click'); await flushPromises()
    expect(w.get('[aria-label="主管成本与账单预览"]').text()).toContain('原应付待核实，差额待核实')
    expect(w.get('[aria-label="主管成本与账单预览"]').text()).not.toContain('应付差额 CNY'); w.unmount()
    mocks.can.mockImplementation(code => code.startsWith('carton_supplier:'))
    vi.mocked(api.detail).mockResolvedValue({ ...correctionRow({ current_unit_price: null, allowed_actions: ['SUPPLIER_CONFIRM'] }), impact })
    const supplier = await opened({ internal: false, factories: [{ factory_id: 'huaxing' }] })
    expect(supplier.find('[aria-label="主管成本与账单预览"]').exists()).toBe(false); expect(supplier.text()).not.toContain('原应付待核实，差额待核实'); supplier.unmount()
  })
  it('finalizes only with latest impact fingerprint and distinguishes successful posting from failed refresh', async () => {
    const w = await opened(); expect(button(w, '主管确认更正生效')).toBeUndefined(); await button(w, '预览成本与账单影响').trigger('click'); await flushPromises()
    await button(w, '主管确认更正生效').trigger('click'); await w.get('[aria-label="单价更正处理依据"]').setValue('核对完整重演影响'); vi.mocked(api.workspace).mockRejectedValueOnce(new Error('清单读取失败'))
    await w.get('form').trigger('submit'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith(true, 'LINE1', expect.objectContaining({ action: 'FINAL_CONFIRM', impact_fingerprint: 'i'.repeat(64), expected_revision: 2 }), expect.any(String), expect.any(AbortSignal))
    expect(w.get('[role="status"]').text()).toContain('更正已生效'); expect(w.get('[role="alert"]').text()).toContain('本次处理已保存'); expect(w.find('form').exists()).toBe(false); expect(w.emitted('changed')).toHaveLength(1); w.unmount()
  })
  it('keeps supplier agreement while a later issue expires only the cost preview and requires another preview', async () => {
    const w = await opened(); await button(w, '预览成本与账单影响').trigger('click'); await flushPromises(); await button(w, '主管确认更正生效').trigger('click'); await w.get('[aria-label="单价更正处理依据"]').setValue('核对最新账序金额')
    vi.mocked(api.act).mockRejectedValueOnce(new Error('成本预览已变化，请重新预览')); await w.get('form').trigger('submit'); await flushPromises()
    expect(w.find('[aria-label="主管成本与账单预览"]').exists()).toBe(false); expect(w.get('[aria-label="单价更正三方流程"]').text()).toContain('2026-10-20T10:00:00+08:00')
    vi.mocked(api.preview).mockResolvedValueOnce({ ...correctionRow(), impact: correctionImpact({ impact_fingerprint: 'new-impact' }) }); await button(w, '预览成本与账单影响').trigger('click'); await flushPromises()
    await button(w, '主管确认更正生效').trigger('click'); await w.get('[aria-label="单价更正处理依据"]').setValue('重新核对最新成本'); await w.get('form').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.act).mock.calls.map(call => call[2].action)).toEqual(['FINAL_CONFIRM', 'FINAL_CONFIRM']); expect(vi.mocked(api.act).mock.calls[1]![2].impact_fingerprint).toBe('new-impact'); w.unmount()
  })
  it('invalidates an edited action when the exact receipt source changes without silently replacing its basis', async () => {
    warehouse(); const w = await opened(); await proposal(w)
    vi.mocked(api.detail).mockResolvedValueOnce(correctionRow({ revision: 4, source_fingerprint: 'changed', status: 'STALE', proposed_unit_price: '3' })); await button(w, '重新读取此批次').trigger('click'); await flushPromises()
    expect(w.get('form').text()).toContain('依据已变化'); expect(w.get<HTMLInputElement>('[aria-label="更正提议新单价"]').element.value).toBe('3.123456')
    await w.get('form').trigger('submit'); expect(api.act).not.toHaveBeenCalled(); expect(w.get('[aria-label="单价更正三方流程"]').text()).toContain('原确认不可继续使用'); w.unmount()
  })
  it('retries the complete original uncertain request after refresh rather than using current source revision', async () => {
    const original = { receipt_line_id: 'LINE1', body: { factory_id: 'huaxing', request_id: 'original-request-123', expected_revision: 1, source_fingerprint: 'old', action: 'FINAL_CONFIRM' as const, impact_fingerprint: 'old-impact', reason: '原已核对成本影响' } }
    vi.mocked(pendingPriceCorrection).mockReturnValue(original); const w = await opened(); expect(button(w, '提出单价更正').attributes('disabled')).toBeDefined(); await button(w, '重试原未确认请求').trigger('click'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith(true, 'LINE1', { factory_id: 'huaxing', expected_revision: 1, source_fingerprint: 'old', action: 'FINAL_CONFIRM', impact_fingerprint: 'old-impact', reason: '原已核对成本影响' }, expect.any(String), expect.any(AbortSignal)); w.unmount()
  })
  it('fences old factory detail and old writes while preserving same-identity heartbeat drafts', async () => {
    warehouse(); const w = await opened(); await proposal(w); const reads = vi.mocked(api.detail).mock.calls.length
    identity.currentUser = { id: 'warehouse' }; await flushPromises(); expect(api.detail).toHaveBeenCalledTimes(reads); expect(w.get<HTMLInputElement>('[aria-label="更正提议新单价"]').element.value).toBe('3.123456')
    let resolveOld!: (row: PriceCorrectionDetail) => void; vi.mocked(api.act).mockImplementationOnce(() => new Promise(done => { resolveOld = done })); await w.get('form').trigger('submit')
    vi.mocked(api.detail).mockResolvedValue(correctionRow({ factory_id: 'huadeng', document_no: '第二厂送货单' })); await w.setProps({ factoryId: 'huadeng' }); await flushPromises()
    resolveOld(correctionRow({ status: 'APPLIED' })); await flushPromises(); expect(w.emitted('changed')).toBeUndefined(); expect(w.text()).not.toContain('本批单价更正已生效'); expect(w.text()).toContain('第二厂送货单'); w.unmount()
  })
  it('does not let an earlier detail response overwrite the successful write result', async () => {
    warehouse(); const w = await opened(); await proposal(w)
    let resolveDetail!: (row: PriceCorrectionDetail) => void
    vi.mocked(api.detail).mockImplementationOnce(() => new Promise(done => { resolveDetail = done }))
    await button(w, '重新读取此批次').trigger('click')
    await w.get('form').trigger('submit'); await flushPromises()
    resolveDetail(correctionRow({ revision: 1, current_unit_price: '123.999', status: 'STALE' })); await flushPromises()
    expect(w.get('[aria-label="原价当前价与提议价"]').text()).not.toContain('123.999')
    expect(w.get('[aria-label="原价当前价与提议价"]').text()).toContain('已生效更正价'); expect(w.find('form').exists()).toBe(false); w.unmount()
  })
  it('gives supplier a published-only empty state and hides internal blocker evidence', async () => {
    mocks.can.mockImplementation(code => code.startsWith('carton_supplier:')); vi.mocked(api.workspace).mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0, pending_count: 0 })
    vi.mocked(api.detail).mockResolvedValue(correctionRow({ allowed_actions: ['SUPPLIER_CONFIRM', 'SUPPLIER_DISPUTE'], blockers: [{ code: 'VALUATION_ERROR', kind: 'VALUATION', message: '内部成本凭证SECRET-COST-001' }] }))
    const w = await opened({ internal: false, factories: [{ factory_id: 'huaxing' }] })
    expect(w.text()).toContain('当前没有供应商可核对的已发布更正方案'); expect(w.text()).not.toContain('仓管可在“全部”'); expect(w.text()).not.toContain('SECRET-COST-001')
    await button(w, '提出价格异议').trigger('click'); await w.get('[aria-label="单价更正处理依据"]').setValue('报价版本有误请复核'); await w.get('form').trigger('submit'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith(false, 'LINE1', expect.objectContaining({ action: 'SUPPLIER_DISPUTE' }), expect.any(String), expect.any(AbortSignal)); w.unmount()
  })
})
