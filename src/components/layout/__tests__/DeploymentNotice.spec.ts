import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DeploymentNotice from '../DeploymentNotice.vue'
import { parseDeploymentNotice } from '@/lib/deploymentNotice'

const id = 'a'.repeat(32)
const start = '2026-10-07T04:05:00Z'
const state = (phase = 'scheduled') => ({ id, phase, starts_at: start, expires_at: phase === 'completed' ? '2026-10-07T04:30:00Z' : undefined, message: '请保存当前内容' })
const response = (payload: unknown, date = 'Wed, 07 Oct 2026 04:00:00 GMT') => ({ ok: true, json: async () => payload, headers: new Headers({ Date: date }) })
let wrapper: ReturnType<typeof mount>
let request: ReturnType<typeof vi.fn>
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-07T04:00:00Z'))
  request = vi.fn().mockResolvedValue(response(state()))
  vi.stubGlobal('fetch', request)
})
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); document.body.innerHTML = '' })
async function load() { wrapper = mount(DeploymentNotice, { attachTo: document.body }); await flushPromises() }
async function click(text: string) {
  const button = Array.from(document.querySelectorAll('button')).find(button => button.textContent?.includes(text))
  expect(button).toBeDefined(); button!.click(); await flushPromises()
}

describe('all-user deployment notice', () => {
  it('shows five minutes, allows saving and never infers maintenance from zero', async () => {
    await load()
    expect(document.body.textContent).toContain('05:00')
    await click('知道了，先保存')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.body.textContent).toContain('停机倒计时')
    // Cached server Date advances with each response in real use.
    request.mockRejectedValue(new Error('offline'))
    await vi.advanceTimersByTimeAsync(300000)
    expect(document.body.textContent).toContain('等待更新开始')
    expect(document.body.textContent).not.toContain('系统正在维护')
  })

  it('keeps maintenance visible during disconnect and offers an explicit refresh after recovery', async () => {
    request.mockResolvedValue(response(state('maintenance')))
    await load()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(document.body.textContent).not.toContain('知道了，先保存')
    request.mockRejectedValue(new Error('restarting'))
    await vi.advanceTimersByTimeAsync(10000)
    expect(document.body.textContent).toContain('系统正在维护')
    expect(document.body.textContent).toContain('等待服务器恢复连接')
    request.mockResolvedValue(response(state('completed')))
    await vi.advanceTimersByTimeAsync(10000)
    expect(document.body.textContent).toContain('系统已恢复')
    expect(document.body.textContent).toContain('我已保存，刷新页面')
    await click('保留当前页面')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('uses server time even when the device clock is wrong', async () => {
    vi.setSystemTime(new Date('2026-10-07T06:00:00Z'))
    await load()
    expect(document.body.textContent).toContain('05:00')
  })

  it('announces a cancelled deployment and does not repeat an acknowledged popup', async () => {
    await load()
    request.mockResolvedValue(response({ ...state('cancelled'), expires_at: '2026-10-07T04:15:00Z' }))
    await vi.advanceTimersByTimeAsync(10000)
    expect(document.body.textContent).toContain('更新已取消')
    expect(document.body.textContent).not.toContain('我已保存，刷新页面')
    await click('保留当前页面')
    await vi.advanceTimersByTimeAsync(10000)
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('does not clear an active notice on malformed responses or inject notice HTML', async () => {
    request.mockResolvedValue(response({ ...state('maintenance'), message: '<img src=x onerror=alert(1)>' }))
    await load()
    expect(document.body.textContent).toContain('<img src=x onerror=alert(1)>')
    expect(document.querySelector('img')).toBeNull()
    request.mockResolvedValue(response({ phase: 'completed' }))
    await vi.advanceTimersByTimeAsync(10000)
    expect(document.body.textContent).toContain('系统正在维护')
    expect(parseDeploymentNotice({ ...state('completed'), expires_at: 'invalid' })).toBeNull()
  })

  it('expires a completed notice, and stops polling when unmounted', async () => {
    request.mockResolvedValue(response({ ...state('completed'), expires_at: '2026-10-07T04:00:02Z' }))
    await load()
    await vi.advanceTimersByTimeAsync(2000)
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    wrapper.unmount()
    const calls = request.mock.calls.length
    await vi.advanceTimersByTimeAsync(30000)
    expect(request.mock.calls.length).toBe(calls)
  })
})
