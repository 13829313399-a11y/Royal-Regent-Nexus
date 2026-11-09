import { describe, expect, it } from 'vitest'
import { getApiErrorMessage, http } from './http'

describe('local JP HTTP boundary', () => {
  it('keeps all requests on the local API and leaves multipart boundaries to Axios', async () => {
    const payload = new FormData()
    payload.append('factory_id', 'huakang-b')
    let sent: unknown
    let contentType: unknown
    await http.post('/huakang-b-jp/preview', payload, {
      adapter: async config => {
        sent = config.data
        contentType = config.headers.getContentType()
        expect(config.baseURL).toBe('/api')
        expect(config.withCredentials).toBe(false)
        return { status: 200, statusText: 'OK', headers: {}, config, data: {} }
      },
    })
    expect(sent).toBe(payload)
    expect(contentType).not.toBe('application/json')
  })

  it('keeps server validation evidence and does not treat a timeout as a confirmed failed save', () => {
    expect(getApiErrorMessage({ isAxiosError: true, response: { status: 409, data: { detail: '参照已变更，请重新核对' } } })).toBe('参照已变更，请重新核对')
    expect(getApiErrorMessage({ isAxiosError: true, response: { status: 422, data: { detail: [{ msg: 'Field required' }] } } })).toBe('必填项未填写')
    const timeout = getApiErrorMessage({ isAxiosError: true, code: 'ECONNABORTED' })
    expect(timeout).toContain('结果尚未确认')
    expect(timeout).toContain('历史导出记录')
    expect(getApiErrorMessage({ isAxiosError: true, code: 'ERR_NETWORK' })).toContain('本地试用服务')
  })
})
