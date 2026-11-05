// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { assertOperationAllowed, downloadBuffer, invalidateSession, loadPrivateTemplate, startSession } from './session.js'

const context = (factory = 'huakang-a') => ({
  factory_id: factory, user_id: 'user-a', employment_epoch: 1, templates: { '/hka-tpl/华康A-zuru.xlsx': 'a-zuru' },
})
let fetchMock
beforeEach(() => {
  invalidateSession()
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
const response = (data) => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })

describe('private invoice session', () => {
  it('rejects unsupported factories before fetching', async () => {
    for (const factory of ['group', 'huakang-c', 'huaxing', 'xingxin', null]) {
      await expect(startSession(factory)).rejects.toThrow('第一版')
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('does not fetch a different factory template or fall back to a public path', async () => {
    fetchMock.mockResolvedValue(response(context()))
    await startSession('huakang-a')
    await expect(loadPrivateTemplate('/hkd-tpl/华康D-MAXX.xlsx')).rejects.toThrow('不属于')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('uses authenticated no-store template fetch', async () => {
    fetchMock.mockResolvedValueOnce(response(context())).mockResolvedValueOnce(response(context()))
      .mockResolvedValueOnce(new Response('private-template')).mockResolvedValueOnce(response(context()))
    await startSession('huakang-a')
    expect(new TextDecoder().decode(await loadPrivateTemplate('/hka-tpl/华康A-zuru.xlsx'))).toBe('private-template')
    expect(fetchMock.mock.calls[2][0]).toBe('/api/mainland-invoices/templates/a-zuru?factory_id=huakang-a')
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' })
  })
  it('locks operations after revoked authorization', async () => {
    fetchMock.mockResolvedValueOnce(response(context())).mockResolvedValueOnce(new Response('{"detail":"已撤权"}', { status: 403 }))
    await startSession('huakang-a')
    await expect(assertOperationAllowed()).rejects.toThrow('已撤权')
    await expect(loadPrivateTemplate('/hka-tpl/华康A-zuru.xlsx')).rejects.toThrow('不属于')
  })
  it('discards a late template response after session invalidation', async () => {
    let resolve
    fetchMock.mockResolvedValueOnce(response(context())).mockResolvedValueOnce(response(context()))
      .mockReturnValueOnce(new Promise(r => { resolve = r }))
    await startSession('huakang-a')
    const pending = loadPrivateTemplate('/hka-tpl/华康A-zuru.xlsx')
    const assertion = expect(pending).rejects.toThrow('会话已失效')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    invalidateSession()
    resolve(new Response('stale'))
    await assertion
  })
  it('never downloads stale results after permission failure', async () => {
    fetchMock.mockResolvedValueOnce(response(context())).mockResolvedValueOnce(new Response('{"detail":"拒绝"}', { status: 403 }))
    await startSession('huakang-a')
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click')
    vi.spyOn(window, 'alert').mockImplementation(() => {})
    await downloadBuffer(new Uint8Array([1]), 'test.xlsx')
    expect(click).not.toHaveBeenCalled()
  })
  it.each([{ user_id: 'user-b' }, { employment_epoch: 2 }])('invalidates results when same-factory identity changes: %j', async changed => {
    fetchMock.mockResolvedValueOnce(response(context()))
      .mockResolvedValueOnce(response({ ...context(), ...changed }))
    await startSession('huakang-a')
    await expect(assertOperationAllowed()).rejects.toThrow('账号或任职身份已变化')
    await expect(loadPrivateTemplate('/hka-tpl/华康A-zuru.xlsx')).rejects.toThrow('不属于')
  })
  it('rejects a completed operation from an older session without invalidating the new session', async () => {
    fetchMock.mockImplementation(async () => response(context()))
    await startSession('huakang-a')
    const operation = await assertOperationAllowed()
    expect(await assertOperationAllowed(operation)).toBe(operation)
    await startSession('huakang-a')
    await expect(assertOperationAllowed(operation)).rejects.toThrow('厂区或账号已变化')
    expect(await assertOperationAllowed()).not.toBe(operation)
  })
  it('rejects a context with the wrong factory identity', async () => {
    fetchMock.mockResolvedValue(response(context('huakang-d')))
    await expect(startSession('huakang-a')).rejects.toThrow('错误的厂区')
  })
})
