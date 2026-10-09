import { Blob as NodeBlob } from 'node:buffer'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getApiErrorMessage, getApiErrorMessageAsync, http } from '../http'

afterEach(() => vi.unstubAllGlobals())

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

  it('still explains failures when the thrown value has no usable message', () => {
    for (const error of [new Error(''), new Error('   '), undefined, {}]) {
      expect(getApiErrorMessage(error)).toContain('未取得具体原因')
    }
    expect(getApiErrorMessage('库存不足，请核对结存')).toBe('库存不足，请核对结存')
  })

  it('shows the field and line for request validation failures', () => {
    expect(getApiErrorMessage(createAxiosError({ detail: [
      { loc: ['body', 'customer_code'], msg: 'Field required' },
      { loc: ['body', 'lines', 1, 'unit_price'], msg: 'Input should be greater than 0' },
      { loc: ['body', 'lines', 0, 'received_quantity'], msg: 'Input should be greater than or equal to 0' },
    ] }))).toBe('客户：必填项未填写; 明细 · 第 2 行 · 单价：必须大于 0; 明细 · 第 1 行 · 实收数量：必须大于或等于 0')
  })

  it.each([
    [401, '登录已失效'], [403, '没有此操作的权限'], [413, '上传文件过大'],
    [422, '数据未通过校验'], [500, '服务器处理异常'], [502, '后台服务连接异常'],
  ])('explains HTTP %s when the server provides no reason', (status, reason) => {
    const error = { ...createAxiosError('<html>Internal Server Error</html>'), response: { status, data: undefined } }
    expect(getApiErrorMessage(error)).toContain(reason)
    expect(getApiErrorMessage(error)).toContain(`HTTP ${status}`)
  })

  it('explains network failures and makes timeout results explicitly uncertain', () => {
    expect(getApiErrorMessage({ isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error' })).toContain('无法连接服务器')
    const timeout = getApiErrorMessage({ isAxiosError: true, code: 'ECONNABORTED', message: 'timeout of 15000ms exceeded' })
    expect(timeout).toContain('未能确认操作结果')
    expect(timeout).toContain('历史记录核对')
  })

  it('keeps the backend business reason even when a fallback status exists', () => {
    expect(getApiErrorMessage({ ...createAxiosError({ detail: '订单已完成，不能再次确认' }), response: {
      status: 409, data: { detail: '订单已完成，不能再次确认' },
    } })).toBe('订单已完成，不能再次确认')
  })

  it('reads JSON reasons returned as a failed workbook download', async () => {
    vi.stubGlobal('Blob', NodeBlob)
    const body = new NodeBlob([JSON.stringify({ detail: { message: '采购单已撤销，不能导出' } })], { type: 'application/json' })
    expect(await getApiErrorMessageAsync({ isAxiosError: true, message: 'Request failed with status code 409', response: { status: 409, data: body } }))
      .toBe('采购单已撤销，不能导出')
    expect(await getApiErrorMessageAsync({ isAxiosError: true, message: 'Request failed', response: { status: 500, data: new NodeBlob(['<html>error</html>']) } }))
      .toContain('服务器处理异常')
  })
})
