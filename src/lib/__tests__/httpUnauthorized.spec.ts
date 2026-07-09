import { beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => {
  const state: {
    onRejected?: (error: unknown) => Promise<never>
  } = {}
  const instance = {
    interceptors: {
      response: {
        use: vi.fn((_onFulfilled, onRejected) => {
          state.onRejected = onRejected
        }),
      },
    },
  }
  const axios = {
    create: vi.fn(() => instance),
    isAxiosError: vi.fn((error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError)),
  }

  return { axios, state }
})

vi.mock('axios', () => ({
  default: axiosMock.axios,
}))

describe('http unauthorized handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls the registered unauthorized handler for 401 responses and keeps rejecting the error', async () => {
    const { setUnauthorizedHandler } = await import('../http')
    const handler = vi.fn()
    const error = {
      isAxiosError: true,
      response: {
        status: 401,
        data: { detail: '登录已过期' },
      },
    }

    setUnauthorizedHandler(handler)

    await expect(axiosMock.state.onRejected?.(error)).rejects.toBe(error)
    expect(handler).toHaveBeenCalledOnce()
    expect(handler).toHaveBeenCalledWith(error)
  })
})
