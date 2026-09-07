import { describe, expect, it } from 'vitest'
import { getApiErrorMessage, http } from '../http'

function createAxiosError(data: unknown, message = 'Request failed with status code 409') {
  return {
    isAxiosError: true,
    message,
    response: {
      data,
    },
  }
}

describe('getApiErrorMessage', () => {
  it('extends only quote timeouts and preserves explicit overrides', async () => {
    for (const [url, timeout, expected] of [
      ['/internal-quotes/quote-1/sections/save-all', undefined, 120_000],
      ['/internal-quotes/quote-1/exports', 60_000, 60_000],
      ['/other-api', undefined, 15_000],
    ] as const) {
      await http.get(url, {
        ...(timeout === undefined ? {} : { timeout }),
        adapter: async (config) => {
          expect(config.timeout).toBe(expected)
          return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
        },
      })
    }
  })
  it('uses FastAPI detail strings before the generic Axios status message', () => {
    expect(getApiErrorMessage(createAxiosError({ detail: '啤办单编号已存在' })))
      .toBe('啤办单编号已存在')
  })

  it('keeps supporting message payloads', () => {
    expect(getApiErrorMessage(createAxiosError({ message: '账号不可用' })))
      .toBe('账号不可用')
  })
})
