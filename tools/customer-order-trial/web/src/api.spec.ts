import { afterEach, describe, expect, it } from 'vitest'
import { AxiosError } from 'axios'
import { http, api, errorMessage, getApiErrorMessage } from './api'
const original = http.defaults.adapter
afterEach(() => { http.defaults.adapter = original })
describe('local-only transport', () => {
  it('preserves multipart files and attaches the trial request guard without online auth', async () => {
    const body = new FormData(); body.append('po_files', new File(['source'], '001.pdf'))
    http.defaults.adapter = async config => {
      expect(config.baseURL).toBe('/api')
      expect(config.data).toBe(body)
      expect(config.headers.get('X-Order-Trial')).toBe('1')
      expect(config.headers.get('Authorization')).toBeUndefined()
      expect(config.timeout).toBe(300_000)
      expect(config.withCredentials).toBe(false)
      return { config, data: { rows: [] }, status: 200, statusText: 'OK', headers: {} }
    }
    await api.preview(body)
  })
  it('retains server download names and encryption notices', async () => {
    http.defaults.adapter = async config => ({ config, data: new Blob(['xlsx']), status: 200, statusText: 'OK', headers: { 'content-disposition': "attachment; filename*=UTF-8''%E9%93%B6%E8%BE%89.xlsx", 'x-workbook-password-required': 'true', 'x-export-id': 'export-1' } })
    expect(await api.download('export-1')).toMatchObject({ fileName: '银辉.xlsx', passwordRequired: true, exportId: 'export-1' })
  })
  it('does not claim failure or success for an unknown timeout result', async () => {
    const timeout = new AxiosError('timeout', 'ECONNABORTED')
    expect(getApiErrorMessage(timeout)).toContain('先刷新本机台账')
    expect(await errorMessage(timeout)).toContain('先核对本机台账与排期文件历史')
  })
})
