// @vitest-environment node
import { createServer, type Server } from 'node:http'
import { afterEach, describe, expect, it } from 'vitest'
import { createCustomerOrderApi } from '@/api/customerOrder'
import { http } from '@/lib/http'

const originalBaseURL = http.defaults.baseURL
let server: Server | undefined

afterEach(async () => {
  http.defaults.baseURL = originalBaseURL
  if (server) {
    const current = server
    server = undefined
    await new Promise<void>((resolve, reject) => current.close(error => error ? reject(error) : resolve()))
  }
})

describe('warehouse schedule upload transport', () => {
  it.each(['UPLOADED', 'GENERATED'] as const)('sends %s bytes and fields through the real shared HTTP client', async (sourceKind) => {
    let received: { url?: string; contentType: string; form: FormData } | undefined
    server = createServer(async (request, response) => {
      try {
        const chunks: Buffer[] = []
        for await (const chunk of request) chunks.push(Buffer.from(chunk))
        const contentType = request.headers['content-type'] ?? ''
        const form = await new Request('http://localhost/upload', {
          method: 'POST', headers: { 'Content-Type': contentType },
          body: new Uint8Array(Buffer.concat(chunks)),
        }).formData()
        received = { url: request.url, contentType, form }
        response.writeHead(200, { 'Content-Type': 'application/json' })
        response.end(JSON.stringify({ batch_id: 'transport-test', duplicate: false, message: '已同步' }))
      } catch {
        response.writeHead(422, { 'Content-Type': 'application/json' })
        response.end(JSON.stringify({ detail: 'Expected a multipart upload with factory_id and schedule_file' }))
      }
    })
    await new Promise<void>((resolve, reject) => {
      server!.once('error', reject)
      server!.listen(0, '127.0.0.1', resolve)
    })
    const address = server.address()
    if (!address || typeof address === 'string') throw new Error('Missing test server address')
    http.defaults.baseURL = `http://127.0.0.1:${address.port}/api`
    const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0xff, 0x80, 0x0d, 0x0a])
    const file = new File([bytes], '华兴测试排期.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const result = await createCustomerOrderApi().synchronizeWarehouseSchedule('buzzbee', file, 'huaxing', sourceKind)

    expect(result.batch_id).toBe('transport-test')
    expect(received?.url).toBe('/api/customer-orders/buzzbee/warehouse-schedule')
    expect(received?.contentType).toMatch(/^multipart\/form-data; boundary=.+/)
    expect(received?.form.get('factory_id')).toBe('huaxing')
    expect(received?.form.get('source_kind')).toBe(sourceKind)
    const uploaded = received?.form.get('schedule_file') as File
    expect(uploaded).toBeInstanceOf(File)
    expect(uploaded.name).toBe(file.name)
    expect(uploaded.type).toBe(file.type)
    expect(new Uint8Array(await uploaded.arrayBuffer())).toEqual(bytes)
  })
})
