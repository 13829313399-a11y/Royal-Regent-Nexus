import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonFeedbackCenter from '../CartonFeedbackCenter.vue'

const api = vi.hoisted(() => ({ workspace: vi.fn(), detail: vi.fn(), create: vi.fn(), reply: vi.fn(), publish: vi.fn(), image: vi.fn() }))
const capture = vi.hoisted(() => vi.fn())
vi.mock('@/api/cartonFeedback', () => ({ cartonFeedbackApi: api }))
vi.mock('@/lib/feedbackScreenshot', () => ({ captureFeedbackScreenshot: capture }))
const row = { id: 'fb1', factory_id: 'huaxing', author_id: 'u1', author_name: '员工', title: '数量问题', description: '希望修正', context_path: '/module', status: 'OPEN', revision: 1, created_at: '2026-10-05T10:00:00', updated_at: '2026-10-05T10:00:00', images: [], replies: [] }
const root = { props: ['open'], template: '<div v-if="open"><slot /></div>' }
const slot = { template: '<div><slot /></div>' }
const stubs = { Teleport: true, DialogPortal: slot, DialogRoot: root, DialogOverlay: slot, DialogContent: slot, DialogTitle: slot, DialogDescription: slot,
  FeedbackScreenshotAnnotator: { emits: ['save', 'cancel'], template: '<button aria-label="保存测试批注" @click="$emit(\'save\', newFile, [\'1. 数字不正确\'])">批注</button>',
    data: () => ({ newFile: new File(['png'], 'annotated.png', { type: 'image/png' }) }) } }
function setup() { return mount(CartonFeedbackCenter, { props: { factoryId: 'huaxing', factoryName: '华兴', viewerKey: 'u1' }, global: { stubs } }) }
async function button(wrapper: ReturnType<typeof setup>, text: string) { await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click'); await flushPromises() }
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() })
  api.workspace.mockResolvedValue({ can_manage: false, feedbacks: [row], updates: [] })
  api.detail.mockResolvedValue({ ...row })
  api.image.mockResolvedValue(new Blob(['png'], { type: 'image/png' }))
})

describe('private carton feedback and published feature updates', () => {
  it('offers one shared entry and scopes supplier drafts, details and updates to a service factory', async () => {
    api.workspace.mockResolvedValue({ can_manage: true, feedbacks: [row], updates: [] })
    api.create.mockResolvedValue(row)
    const wrapper = mount(CartonFeedbackCenter, { props: { factoryId: '', factoryName: '供应商', supplier: true,
      viewerKey: 'supplier', supplierFactories: [{ id: 'huaxing', name: '华兴' }, { id: 'huakang-a', name: '华康A' }] }, global: { stubs } })
    expect(wrapper.findAll('button')).toHaveLength(1)
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('处理反馈')
    expect(api.workspace).toHaveBeenLastCalledWith('huaxing', false, expect.any(AbortSignal), expect.objectContaining({ portal: 'supplier' }))
    await wrapper.get('input[maxlength="120"]').setValue('旧厂草稿')
    await wrapper.get('[aria-label="反馈所属服务厂区"]').setValue('huakang-a'); await flushPromises()
    expect(wrapper.get('input[maxlength="120"]').element.value).toBe('')
    await wrapper.get('input[maxlength="120"]').setValue('接单问题'); await wrapper.get('textarea').setValue('说明')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create).toHaveBeenCalledWith('huakang-a', '接单问题', '说明', '/carton-supplier', expect.any(String), [], expect.any(AbortSignal), 'supplier')
    expect(api.detail).toHaveBeenCalledWith('huakang-a', 'fb1', expect.any(AbortSignal), 'supplier')
    await button(wrapper, '功能变动')
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })

  it('includes the publication audience in admin retries and queries', async () => {
    api.workspace.mockResolvedValue({ can_manage: true, feedbacks: [], updates: [] })
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises(); await button(wrapper, '功能变动')
    await wrapper.get('input[maxlength="120"]').setValue('新入口'); await wrapper.get('textarea').setValue('右上角打开反馈')
    api.publish.mockRejectedValue(new Error('未确认'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const key = api.publish.mock.calls[0]![3]
    await wrapper.get('[aria-label="更新说明发布对象"]').setValue('SUPPLIER')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.publish.mock.calls[1]![3]).not.toBe(key)
    expect(api.publish.mock.calls[1]![5]).toBe('SUPPLIER')
    await button(wrapper, '刷新更新')
    expect(api.workspace).toHaveBeenLastCalledWith('huaxing', false, expect.any(AbortSignal), expect.objectContaining({ updates_audience: 'SUPPLIER' }))
    wrapper.unmount()
  })
  it('submits annotated screenshots as multipart API inputs and reuses the key when retrying unchanged content', async () => {
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('处理反馈')
    await wrapper.get('input[maxlength="120"]').setValue('页面问题')
    await wrapper.get('textarea').setValue('数量显示异常')
    const fileInput = wrapper.get('input[type=file]')
    Object.defineProperty(fileInput.element, 'files', { configurable: true, value: [new File(['png'], 'screen.png', { type: 'image/png' })] })
    await fileInput.trigger('change'); await wrapper.get('[aria-label="保存测试批注"]').trigger('click'); await flushPromises()
    api.create.mockRejectedValueOnce(new Error('网络未确认')).mockResolvedValueOnce({ ...row })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('网络未确认')
    const first = api.create.mock.calls[0]!
    expect(first.slice(0, 3)).toEqual(['huaxing', '页面问题', '数量显示异常\n截图 1 批注：\n1. 数字不正确'])
    expect((first[5] as File[])[0]!.name).toBe('annotated.png')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.create.mock.calls[1]![4]).toBe(first[4])
    expect(wrapper.text()).toContain('反馈已提交')
    expect(wrapper.text()).toContain('等待管理员处理')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test')
    wrapper.unmount()
  })

  it('requires an admin reply, preserves it after conflicts and publishes updates to the current factory', async () => {
    api.workspace.mockResolvedValue({ can_manage: true, feedbacks: [row], updates: [] })
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises()
    await button(wrapper, '处理反馈')
    expect(api.workspace).toHaveBeenLastCalledWith('huaxing', true, expect.any(AbortSignal), expect.objectContaining({ limit: 25, offset: 0 }))
    await wrapper.get('[aria-label="查看反馈：数量问题"]').trigger('click'); await flushPromises()
    const form = wrapper.get('form')
    expect(form.get('button').attributes('disabled')).toBeDefined()
    await form.get('select').setValue('DECLINED'); await form.get('textarea').setValue('原系统没有可用接口，需要稍后处理。')
    api.reply.mockRejectedValueOnce(new Error('反馈已被更新，请刷新后重新回复'))
    await form.trigger('submit'); await flushPromises()
    expect(api.reply).toHaveBeenCalledWith('huaxing', row, '原系统没有可用接口，需要稍后处理。', 'DECLINED', expect.any(AbortSignal))
    expect(form.get('textarea').element.value).toContain('原系统没有可用接口')
    await button(wrapper, '功能变动')
    expect(wrapper.text()).toContain('发布更新说明到华兴')
    await wrapper.get('input[maxlength="120"]').setValue('看板更新'); await wrapper.get('textarea').setValue('四张统计卡可点击。')
    api.publish.mockResolvedValue({ id: 'up1' })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.publish).toHaveBeenCalledWith('huaxing', '看板更新', '四张统计卡可点击。', expect.any(String), expect.any(AbortSignal), 'INTERNAL')
    expect(wrapper.text()).toContain('更新说明已发布到华兴')
    wrapper.unmount()
  })

  it('shows employee replies and escapes release-note HTML without granting publishing controls', async () => {
    api.detail.mockResolvedValue({ ...row, images: ['image1'], replies: [{ id: 'r1', author_name: '管理员', status: 'FIXED', body: '已修正数字', created_at: row.created_at }] })
    api.workspace.mockResolvedValue({ can_manage: false, feedbacks: [row], updates: [{ id: 'u1', title: '更新', body: '<script>bad()</script>', author_name: '管理员', created_at: row.created_at }] })
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises(); await button(wrapper, '我的反馈')
    await wrapper.get('[aria-label="查看反馈：数量问题"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('已修改 · 管理员'); expect(wrapper.text()).toContain('已修正数字')
    expect(api.image).toHaveBeenCalledWith('huaxing', 'fb1', 'image1', expect.any(AbortSignal))
    expect(wrapper.find('form').exists()).toBe(false)
    await button(wrapper, '功能变动')
    expect(wrapper.text()).toContain('<script>bad()</script>'); expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })

  it('clears private drafts and ignores late details when the viewer or factory changes', async () => {
    let finish: (value: object) => void = () => {}
    api.detail.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises()
    await wrapper.get('input[maxlength="120"]').setValue('私密标题'); await button(wrapper, '我的反馈')
    await wrapper.get('[aria-label="查看反馈：数量问题"]').trigger('click')
    const signal = api.detail.mock.calls[0]![2] as AbortSignal
    await wrapper.setProps({ viewerKey: 'u2', factoryId: 'huakang-a', factoryName: '华康A' })
    finish({ ...row, description: '旧厂区私密问题' }); await flushPromises()
    expect(signal.aborted).toBe(true); expect(wrapper.text()).not.toContain('旧厂区私密问题')
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises()
    expect(wrapper.get('input[maxlength="120"]').element.value).toBe('')
    expect(api.workspace).toHaveBeenLastCalledWith('huakang-a', false, expect.any(AbortSignal), expect.objectContaining({ limit: 25, offset: 0 }))
    wrapper.unmount()
  })

  it('does not attach a capture completed after cancellation', async () => {
    let finish: (value: File) => void = () => {}
    capture.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises()
    await button(wrapper, '截取当前页面')
    const signal = capture.mock.calls[0]![0] as AbortSignal
    await button(wrapper, '取消')
    finish(new File(['private'], 'screen.png', { type: 'image/png' })); await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(wrapper.find('[aria-label="保存测试批注"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('clears cached private details and screenshots when permission refresh fails', async () => {
    api.workspace.mockResolvedValue({ can_manage: true, feedbacks: [row], updates: [] })
    api.detail.mockResolvedValue({ ...row, description: '另一个员工的私密说明', images: ['image1'] })
    const wrapper = setup()
    await wrapper.get('[aria-label="打开反馈与变更"]').trigger('click'); await flushPromises(); await button(wrapper, '处理反馈')
    await wrapper.get('[aria-label="查看反馈：数量问题"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('另一个员工的私密说明')
    api.workspace.mockRejectedValueOnce(new Error('权限已撤销'))
    await button(wrapper, '刷新列表')
    expect(wrapper.text()).not.toContain('另一个员工的私密说明')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test')
    expect(wrapper.text()).toContain('权限已撤销')
    wrapper.unmount()
  })
})
