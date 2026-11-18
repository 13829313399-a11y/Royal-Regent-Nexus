// @vitest-environment node
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, it } from 'vitest'
import { http } from '@/lib/http'
import { huakangBJPApi as api } from '../huakangBJP'

it('sends a decodable multipart body including the file through the real Axios HTTP adapter', async () => {
  let received: FormData | undefined
  let contentType = ''
  let intakeHeader = ''
  const server = createServer(async (req, res) => {
    try {
      const chunks: Buffer[] = []
      for await (const chunk of req) chunks.push(Buffer.from(chunk))
      contentType = String(req.headers['content-type'])
      intakeHeader = String(req.headers['x-jp-intake'])
      const request = new Request('http://localhost/upload', {
        method: 'POST', headers: { 'Content-Type': contentType }, body: Buffer.concat(chunks),
      })
      received = await request.formData()
      res.writeHead(200, { 'Content-Type': 'application/json' }).end('{}')
    } catch {
      res.writeHead(400).end('Invalid multipart body')
    }
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const originalBase = http.defaults.baseURL
  const originalAdapter = http.defaults.adapter
  try {
    http.defaults.baseURL = `http://127.0.0.1:${(server.address() as AddressInfo).port}/api`
    http.defaults.adapter = 'http'
    const form = new FormData()
    form.append('factory_id', 'huakang-b')
    form.append('expected_revision', '3')
    form.append('file', new File(['original workbook bytes'], 'price.xlsx'))
    await api.upload('price', form)
    expect(contentType).toMatch(/^multipart\/form-data; boundary=/)
    expect(intakeHeader).toBe('1')
    expect(received?.get('factory_id')).toBe('huakang-b')
    expect(received?.get('expected_revision')).toBe('3')
    expect(await (received?.get('file') as File).text()).toBe('original workbook bytes')
  } finally {
    http.defaults.baseURL = originalBase
    http.defaults.adapter = originalAdapter
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
})
