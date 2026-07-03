import { describe, expect, it } from 'vitest'
import { getApiErrorMessage } from '../http'

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
  it('uses FastAPI detail strings before the generic Axios status message', () => {
    expect(getApiErrorMessage(createAxiosError({ detail: '啤办单编号已存在' })))
      .toBe('啤办单编号已存在')
  })

  it('keeps supporting message payloads', () => {
    expect(getApiErrorMessage(createAxiosError({ message: '账号不可用' })))
      .toBe('账号不可用')
  })
})
