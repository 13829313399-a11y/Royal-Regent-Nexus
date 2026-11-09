// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import App from './App'
vi.mock('./pages/FactoryHka', () => ({ default: () => <div>A 的上传和输出状态</div> }))
vi.mock('./pages/FactoryHkb', () => ({ default: () => <div>B 的上传和输出状态</div> }))
vi.mock('./pages/FactoryHkd', () => ({ default: () => <div>D 的上传和输出状态</div> }))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
const context = () => new Response(JSON.stringify({ factory_id: 'huakang-a', user_id: 'user-a', employment_epoch: 1, templates: {} }))
describe('invoice UI session invalidation', () => {
  it('does not mount a factory page when authorization fails', async () => {
    window.history.replaceState({}, '', '?factory_id=huakang-a')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"没有权限"}', { status: 403 })))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('没有权限'))
    expect(screen.queryByText('A 的上传和输出状态')).toBeNull()
  })
  it('unmounts uploaded data and outputs on a failed focus recheck', async () => {
    window.history.replaceState({}, '', '?factory_id=huakang-a')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(context())
      .mockResolvedValue(new Response('{"detail":"已撤权"}', { status: 403 })))
    render(<App />)
    await waitFor(() => expect(screen.getByText('A 的上传和输出状态')).toBeTruthy())
    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(screen.queryByText('A 的上传和输出状态')).toBeNull())
    expect(screen.getByRole('status').textContent).toContain('权限已失效')
  })
})
