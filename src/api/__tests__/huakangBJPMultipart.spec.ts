import { afterEach, describe, expect, it } from 'vitest'
import { http } from '@/lib/http'
import { huakangBJPApi as api } from '../huakangBJP'

const originalAdapter = http.defaults.adapter
afterEach(() => { http.defaults.adapter = originalAdapter })

describe('JP multipart transport through the real shared HTTP client', () => {
  it.each(['upload', 'preview', 'export', 'clearConfirmed'] as const)('preserves form fields and file bytes for %s', async action => {
    const form = new FormData()
    form.append('factory_id', 'huakang-b')
    form.append('expected_revision', '0')
    form.append('file', new File(['workbook bytes'], 'price.xlsx'))
    let inspected = false
    // Axios runs its actual transformRequest before calling this adapter.
    http.defaults.adapter = async config => {
      inspected = true
      expect(config.data).toBe(form)
      expect(config.data.get('factory_id')).toBe('huakang-b')
      expect(config.data.get('expected_revision')).toBe('0')
      expect(config.data.get('file').name).toBe('price.xlsx')
      expect(config.headers.get('Content-Type')).toBe('multipart/form-data')
      expect(config.headers.get('X-JP-Intake')).toBe('1')
      expect(config.withCredentials).toBe(true)
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    }
    if (action === 'upload') await api.upload('price', form)
    else await api[action](form)
    expect(inspected).toBe(true)
  })
})
