// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { compileStyle, parse } from '@vue/compiler-sfc'

const state = vi.hoisted(() => ({
  route: { path: '/modules/qc/inspection-operations', hash: '', query: {} as Record<string, string> },
  app: { activeFactoryId: 'group' },
  auth: { currentUser: { id: 'one' }, authorizationVersion: 1 },
  get: vi.fn(), replace: vi.fn(), can: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => state.route, useRouter: () => ({ replace: state.replace }), RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('@/stores/app', () => ({ useAppStore: () => state.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => new Proxy(state.auth, { get: (target, key) => key === 'can' ? state.can : Reflect.get(target, key) }) }))
vi.mock('@/lib/http', () => ({ http: { get: state.get }, getApiErrorMessage: (error: Error) => error.message }))
import Host from '@/views/QcOperationsCenterView.vue'
import { canChangeFactory } from '@/lib/factoryChangeGuard'

beforeEach(() => {
  state.route = reactive({ path: '/modules/qc/inspection-operations', hash: '', query: {} })
  state.app = reactive({ activeFactoryId: 'group' })
  state.auth = reactive({ currentUser: { id: 'one' }, authorizationVersion: 1 })
  state.get.mockReset()
  state.can.mockReset().mockReturnValue(true)
  state.replace.mockReset().mockImplementation(async (destination) => {
    if (!canChangeFactory()) return
    state.app.activeFactoryId = destination.query.factory
    state.route.query = destination.query
  })
})

describe('QC_department host', () => {
  it('does not default a group context to another factory', async () => {
    const wrapper = mount(Host)
    await flushPromises()
    expect(state.get).not.toHaveBeenCalled()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('选择具体厂区')
    wrapper.unmount()
  })
  it('embeds the authorized URL and reloads on same-factory account changes', async () => {
    state.route.query.factory = 'huaxing'
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
    const wrapper = mount(Host)
    await flushPromises()
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/qc-department/huaxing/u-one/')
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-two/' } })
    state.auth.currentUser.id = 'two'
    await flushPromises()
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/qc-department/huaxing/u-two/')
    expect(state.get).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('keeps the connection message until the current frame loads, including on reload', async () => {
    state.route.query.factory = 'huaxing'
    let resolveHealth!: (value: unknown) => void
    state.get.mockReturnValueOnce(new Promise(resolve => { resolveHealth = resolve }))
    const wrapper = mount(Host)
    try {
      expect(wrapper.get('[role="status"]').text()).toContain('正在连接 QC 工作台')
      expect(wrapper.get('[role="status"] .qc-orbit').attributes('aria-hidden')).toBe('true')
      expect(wrapper.find('iframe').exists()).toBe(false)
      resolveHealth({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
      await flushPromises()
      const firstFrame = wrapper.get('iframe')
      expect(firstFrame.classes()).toContain('invisible')
      expect(wrapper.get('[role="status"]').text()).toContain('正在连接 QC 工作台')
      expect(wrapper.get('button').attributes('disabled')).toBeUndefined()

      state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
      await wrapper.get('button').trigger('click')
      await flushPromises()
      const secondFrame = wrapper.get('iframe')
      expect(secondFrame.element).not.toBe(firstFrame.element)
      await firstFrame.trigger('load')
      expect(secondFrame.classes()).toContain('invisible')
      expect(wrapper.find('[role="status"]').exists()).toBe(true)
      const { bridge } = bridgeFor(wrapper)
      await secondFrame.trigger('load')
      expect(bridge.page).toBe('sales-schedule')
      expect(secondFrame.classes()).not.toContain('invisible')
      expect(wrapper.find('[role="status"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })
  it('removes the old frame while rechecking a changed authorization version', async () => {
    state.route.query.factory = 'huaxing'
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
    const wrapper = mount(Host)
    await flushPromises()
    state.get.mockRejectedValueOnce(new Error('当前账号没有权限'))
    state.auth.authorizationVersion++
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('没有权限')
    wrapper.unmount()
  })
  it('does not apply a late response from the previous factory', async () => {
    state.route.query.factory = 'huaxing'
    let resolveFirst!: (value: unknown) => void
    state.get.mockReturnValueOnce(new Promise(resolve => { resolveFirst = resolve }))
    const wrapper = mount(Host)
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huakang-a/u-one/' } })
    state.route.query.factory = 'huakang-a'
    await nextTick()
    await flushPromises()
    resolveFirst({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
    await flushPromises()
    expect(wrapper.find('iframe').attributes('src')).toContain('/huakang-a/')
    wrapper.unmount()
  })
})

function bridgeFor(wrapper: ReturnType<typeof mount>) {
  const iframe = wrapper.get('iframe').element as HTMLIFrameElement
  // Detached jsdom iframes do not create a browsing context.
  Object.defineProperty(iframe, 'contentWindow', { configurable: true, value: {} })
  const bridge = { factory: '', page: '', options: [] as {id: string; label: string}[], select: async (_: string) => {} }
  Object.assign(iframe.contentWindow!, {
    __QC_SET_FACTORY_BRIDGE: (value: typeof bridge) => Object.assign(bridge, value),
    __QC_CONFIRM_FACTORY_LEAVE: vi.fn().mockReturnValue(true),
    __QC_CURRENT_PAGE: () => 'sales-schedule',
  })
  return { iframe, bridge }
}
function health() {
  state.get.mockImplementation(async (url: string) => ({data:{frame_url:url.replace('/api/health','/u-one/')}}))
}
it('QC selection updates the Nexus context and URL, replacing the old factory frame', async () => {
  state.route.query.factory = 'huaxing'; health()
  const wrapper = mount(Host)
  await flushPromises()
  const { iframe, bridge } = bridgeFor(wrapper)
  await wrapper.get('iframe').trigger('load')
  expect(bridge.factory).toBe('huaxing')
  await bridge.select('huakang-a'); await flushPromises()
  expect(state.app.activeFactoryId).toBe('huakang-a')
  expect(state.route.query.factory).toBe('huakang-a')
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('huakang-a')
  expect(wrapper.get('iframe').element).not.toBe(iframe)
  expect(wrapper.get('iframe').attributes('src')).toContain('/huakang-a/')
  const next = bridgeFor(wrapper)
  await wrapper.get('iframe').trigger('load')
  expect(next.bridge.page).toBe('sales-schedule')
  await bridge.select('huadeng') // A detached frame cannot switch the current factory.
  expect(state.route.query.factory).toBe('huakang-a')
  wrapper.unmount()
})
it('Nexus selection and group clear the previous frame without fetching group data', async () => {
  state.route.query.factory = 'huaxing'; health()
  const wrapper = mount(Host)
  await flushPromises()
  await wrapper.get('select').setValue('huakang-b'); await flushPromises()
  expect(state.app.activeFactoryId).toBe('huakang-b')
  expect(wrapper.get('iframe').attributes('src')).toContain('/huakang-b/')
  state.get.mockClear()
  await wrapper.get('select').setValue('group'); await flushPromises()
  expect(state.app.activeFactoryId).toBe('group')
  expect(wrapper.find('iframe').exists()).toBe(false)
  expect(state.get).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('请选择具体厂区')
  wrapper.unmount()
})
it('cancelled changes preserve both selectors, URL, frame and current edits', async () => {
  state.route.query.factory = 'huaxing'; state.app.activeFactoryId = 'huaxing'; health()
  const wrapper = mount(Host)
  await flushPromises()
  const {iframe, bridge} = bridgeFor(wrapper)
  const guard = vi.fn().mockReturnValue(false)
  Object.assign(iframe.contentWindow!, {__QC_CONFIRM_FACTORY_LEAVE:guard})
  await wrapper.get('iframe').trigger('load')
  await bridge.select('huakang-a'); await flushPromises()
  await wrapper.get('select').setValue('group'); await flushPromises()
  expect(guard).toHaveBeenCalledTimes(2)
  expect(state.app.activeFactoryId).toBe('huaxing')
  expect(state.route.query.factory).toBe('huaxing')
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('huaxing')
  expect(wrapper.get('iframe').element).toBe(iframe)
  expect(state.get).toHaveBeenCalledTimes(1)
  wrapper.unmount()
  expect(canChangeFactory()).toBe(true)
})
it('QC options are limited to readable factories and cannot request another factory', async () => {
  state.route.query.factory = 'huaxing'; health()
  state.can.mockImplementation((_p, factory) => factory === 'huaxing')
  const wrapper = mount(Host)
  await flushPromises()
  const {bridge} = bridgeFor(wrapper)
  await wrapper.get('iframe').trigger('load')
  expect(bridge.options.map(option=>option.id)).toEqual(['group','huaxing'])
  await bridge.select('huakang-d')
  expect(state.replace).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('authorization refresh reconnects options without resetting the current QC page', async () => {
  state.route.query = { factory: 'huaxing', qcPage: 'dashboard' };health()
  state.can.mockImplementation(() => Boolean(state.auth.currentUser.id))
  const wrapper=mount(Host);await flushPromises()
  const {bridge}=bridgeFor(wrapper);await wrapper.get('iframe').trigger('load')
  expect(bridge.page).toBe('dashboard')
  state.auth.currentUser={id:'one'};await flushPromises()
  expect(bridge.page).toBe('sales-schedule')
  wrapper.unmount()
})


it('restores the QC module from the URL and preserves factory on navigation', async () => {
  state.route.query = { factory: 'huaxing', qcPage: 'inspection-summary' }
  state.get.mockResolvedValue({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
  const wrapper = mount(Host)
  await flushPromises()
  const bridge = vi.fn()
  const { iframe } = bridgeFor(wrapper)
  Object.assign(iframe.contentWindow!, { __QC_SET_FACTORY_BRIDGE: bridge })
  await wrapper.get('iframe').trigger('load')
  expect(bridge.mock.calls[0]?.[0].page).toBe('inspection-summary')
  bridge.mock.calls[0]?.[0].navigate('review')
  await flushPromises()
  expect(state.route.query).toEqual({ factory: 'huaxing', qcPage: 'review' })
  wrapper.unmount()
})

it('tracks rotation, browser chrome and keyboard viewport without recreating the frame; removes listeners on leave', async () => {
  state.route.query.factory='huaxing';health()
  const viewport=new EventTarget() as EventTarget & {height:number;scale:number;offsetTop:number}
  Object.assign(viewport,{height:720,scale:1,offsetTop:0})
  const previous=Object.getOwnPropertyDescriptor(window,'visualViewport')
  Object.defineProperty(window,'visualViewport',{configurable:true,value:viewport})
  const raf=vi.spyOn(window,'requestAnimationFrame').mockImplementation(cb=>{cb(0);return 1})
  const cancel=vi.spyOn(window,'cancelAnimationFrame').mockImplementation(()=>{})
  const wrapper=mount(Host)
  try{
    await flushPromises();const frame=wrapper.get('iframe').element
    expect(document.documentElement.classList.contains('qc-viewport-locked')).toBe(true)
    expect(wrapper.attributes('style')).toContain('--qc-viewport-height: 720px')
    viewport.height=320;window.dispatchEvent(new Event('orientationchange'));await nextTick()
    expect(wrapper.attributes('style')).toContain('--qc-viewport-height: 320px')
    viewport.height=220;viewport.offsetTop=35;viewport.dispatchEvent(new Event('resize'));await nextTick()
    expect(wrapper.attributes('style')).toContain('--qc-viewport-height: 220px')
    expect(wrapper.attributes('style')).toContain('--qc-viewport-top: 35px')
    viewport.scale=2;viewport.height=110;viewport.dispatchEvent(new Event('resize'));await nextTick()
    expect(wrapper.attributes('style')).toContain('--qc-viewport-height: 220px')
    expect(wrapper.get('iframe').element).toBe(frame);expect(state.get).toHaveBeenCalledTimes(1)
    wrapper.unmount();raf.mockClear();viewport.dispatchEvent(new Event('resize'));window.dispatchEvent(new Event('resize'))
    expect(raf).not.toHaveBeenCalled();expect(document.documentElement.classList.contains('qc-viewport-locked')).toBe(false)
  }finally{
    wrapper.unmount();raf.mockRestore();cancel.mockRestore()
    if(previous)Object.defineProperty(window,'visualViewport',previous);else Reflect.deleteProperty(window,'visualViewport')
  }
})

it('uses a native header in both phone tables, synchronizes columns and preserves drafts through layout changes', async () => {
  state.route.query = { factory: 'huaxing', qcPage: 'records' }; health()
  const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(cb => { cb(0); return 1 })
  const cancel = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
  const disconnect = vi.fn()
  let resized = () => {}
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resized = callback }
    observe() {}
    disconnect = disconnect
  })
  const wrapper = mount(Host)
  try {
    await flushPromises()
    const { iframe } = bridgeFor(wrapper)
    const doc = document.implementation.createHTMLDocument('QC')
    Object.defineProperty(doc, 'defaultView', { value: window })
    doc.documentElement.classList.add('qc-mobile')
    doc.body.innerHTML = '<div class="main-wrap"><section id="page-records" class="page active"><div class="qis-wrap"><table class="qis-table"><thead><tr><th data-column="customer" style="left:0px">客户</th><th data-column="poNo" style="left:79px">PO#</th><th data-column="result">验货结果</th></tr></thead><tbody><tr><td><input value="保留正在填写的内容"></td></tr></tbody></table></div></section><section id="page-review" class="page"></section></div>'
    const main = doc.querySelector('.main-wrap')!
    const input = doc.querySelector('input')!
    const sheet = doc.querySelector<HTMLElement>('.qis-wrap')!
    const table = doc.querySelector('table')!
    const head = table.tHead!
    Object.defineProperty(iframe, 'offsetTop', { value: 48 })
    Object.defineProperty(sheet, 'clientWidth', { value: 320 })
    head.querySelectorAll('th').forEach((th, index) => vi.spyOn(th, 'getBoundingClientRect').mockReturnValue({ width: [79, 97, 128][index], height: 34 } as DOMRect))
    let contentHeight = 1000, frameTop = 48
    const measureMain = vi.spyOn(main, 'getBoundingClientRect').mockImplementation(() => ({ height: contentHeight } as DOMRect))
    vi.spyOn(iframe, 'getBoundingClientRect').mockImplementation(() => ({ top: frameTop, bottom: frameTop + contentHeight } as DOMRect))
    vi.spyOn(head.rows[0]!, 'getBoundingClientRect').mockReturnValue({ top: 100, bottom: 134 } as DOMRect)
    vi.spyOn(table, 'getBoundingClientRect').mockImplementation(() => ({ bottom: contentHeight } as DOMRect))
    Object.assign(iframe.contentWindow!, { document: doc })
    await wrapper.get('iframe').trigger('load'); await flushPromises()
    expect(document.documentElement.classList.contains('qc-document-scroll')).toBe(true)
    expect(document.documentElement.classList.contains('qc-viewport-locked')).toBe(false)
    expect(doc.documentElement.classList.contains('qc-page-scroll')).toBe(true)
    expect(iframe.style.height).toBe('1000px')
    const layer = wrapper.get('.qc-table-header-layer').element as HTMLElement
    const bounds = wrapper.get('.qc-table-header-bounds').element as HTMLElement
    const strip = wrapper.get('.qc-table-header-strip').element as HTMLElement
    expect(layer.hidden).toBe(false)
    expect(bounds.style.top).toBe('148px')
    expect(bounds.style.height).toBe('900px') // Native sticky cannot outlive its table.
    expect(bounds.style.width).toBe('320px')
    expect(layer.getAttribute('aria-hidden')).toBe('true')
    expect(layer.hasAttribute('inert')).toBe(true)
    expect(bounds.querySelectorAll('input,button,select,[id],th')).toHaveLength(0)
    expect(Array.from(strip.children).map(el => (el as HTMLElement).style.width)).toEqual(['79px', '97px', '128px'])
    expect((strip.children[1] as HTMLElement).style.left).toBe('79px')
    sheet.scrollLeft = 240; sheet.dispatchEvent(new Event('scroll'))
    expect(strip.scrollLeft).toBe(240)
    const headerNode = strip.firstChild
    measureMain.mockClear()
    frameTop = -350
    window.dispatchEvent(new Event('scroll')); await nextTick()
    expect(doc.documentElement.style.getPropertyValue('--qc-visible-top')).toBe('350px')
    expect(doc.documentElement.style.getPropertyValue('--qc-visible-height')).toBe(`${Math.min(window.innerHeight, 650)}px`)
    expect(bounds.style.top).toBe('148px') // No per-scroll header motion or remeasurement.
    expect(measureMain).not.toHaveBeenCalled()
    expect(strip.firstChild).toBe(headerNode)
    frameTop = -1100; window.dispatchEvent(new Event('scroll')); await nextTick()
    expect(bounds.style.top).toBe('148px')
    frameTop = -350
    contentHeight = 300; resized(); await nextTick()
    expect(iframe.style.height).toBe('300px') // Filtering must release the old blank tail.
    expect(bounds.style.height).toBe('200px')
    expect(wrapper.get('iframe').element).toBe(iframe)
    expect(doc.querySelector('input')).toBe(input)
    expect(input.value).toBe('保留正在填写的内容')
    head.querySelector('[data-column=result]')!.textContent = '更新后的标题'
    await flushPromises()
    expect(strip.textContent).toContain('更新后的标题') // Same-height replacement is observed.
    doc.body.classList.add('qc-sidebar-open'); await flushPromises()
    expect(layer.hidden).toBe(true)
    doc.body.classList.remove('qc-sidebar-open'); await flushPromises()
    expect(layer.hidden).toBe(false)
    const dialog = doc.createElement('dialog'); doc.body.append(dialog)
    dialog.setAttribute('open', ''); await flushPromises()
    expect(layer.hidden).toBe(true)
    dialog.remove(); await flushPromises()
    expect(layer.hidden).toBe(false)
    // Switching out of inspection, or back to desktop, restores the existing workspace.
    doc.querySelector('#page-records')!.classList.remove('active'); await flushPromises()
    expect(iframe.style.height).toBe('')
    expect(document.documentElement.classList.contains('qc-viewport-locked')).toBe(true)
    expect(layer.hidden).toBe(true)
    doc.querySelector('#page-review')!.classList.add('active'); await flushPromises()
    expect(iframe.style.height).toBe('300px')
    const reviewSheet = sheet.cloneNode(true) as HTMLElement
    const reviewTable = reviewSheet.querySelector('table')!
    const reviewHead = reviewTable.tHead!.rows[0]!
    reviewHead.querySelector('[data-column=result]')!.textContent = '审核结果'
    Object.defineProperty(reviewSheet, 'clientWidth', { value: 320 })
    vi.spyOn(reviewHead, 'getBoundingClientRect').mockReturnValue({ top: 20 } as DOMRect)
    vi.spyOn(reviewTable, 'getBoundingClientRect').mockReturnValue({ bottom: 300 } as DOMRect)
    doc.querySelector('#page-review')!.append(reviewSheet); await flushPromises()
    const reviewBounds = wrapper.findAll('.qc-table-header-bounds').map(item => item.element as HTMLElement)
    expect(reviewBounds.map(item => [item.style.top, item.style.height])).toEqual([['68px', '280px']])
    expect(layer.hidden).toBe(false)
    const reviewStrip = wrapper.get('.qc-table-header-strip').element as HTMLElement
    expect(reviewStrip.textContent).toContain('审核结果')
    reviewSheet.scrollLeft = 460; reviewSheet.dispatchEvent(new Event('scroll'))
    expect(reviewStrip.scrollLeft).toBe(460)
    expect(wrapper.findAll('.qc-table-header-strip')).toHaveLength(1)
    sheet.scrollLeft = 900; sheet.dispatchEvent(new Event('scroll'))
    expect(reviewStrip.scrollLeft).toBe(460) // The previous page's listener has been removed.
    doc.documentElement.classList.remove('qc-mobile'); await flushPromises()
    expect(iframe.style.height).toBe('')
    expect(doc.documentElement.classList.contains('qc-page-scroll')).toBe(false)
    expect(layer.hidden).toBe(true)
    expect(layer.children).toHaveLength(0)
    expect(state.get).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalled()
    expect(document.documentElement.classList.contains('qc-document-scroll')).toBe(false)
    raf.mockClear(); window.dispatchEvent(new Event('scroll'))
    expect(raf).not.toHaveBeenCalled()
  } finally {
    wrapper.unmount(); raf.mockRestore(); cancel.mockRestore(); vi.unstubAllGlobals()
  }
})

it('compiles mobile host styles onto the host instead of leaving a fixed outer viewport', () => {
  const source = readFileSync('src/views/QcOperationsCenterView.vue', 'utf8')
  const css = compileStyle({ source: parse(source).descriptor.styles[0]!.content, filename: 'QcOperationsCenterView.vue', id: 'data-v-scroll-test', scoped: true }).code
  const style = document.createElement('style'); style.textContent = css; document.head.append(style)
  const host = document.createElement('main'); host.className = 'qc-department-host'; host.setAttribute('data-v-scroll-test', ''); document.body.append(host)
  try {
    document.documentElement.classList.add('qc-document-scroll')
    expect(getComputedStyle(host).position).toBe('relative')
    expect(getComputedStyle(host).height).toBe('auto')
    expect(getComputedStyle(host).overflow).toBe('visible')
    document.documentElement.classList.remove('qc-document-scroll')
    expect(getComputedStyle(host).position).toBe('fixed')
  } finally { host.remove(); style.remove(); document.documentElement.classList.remove('qc-document-scroll') }
})
