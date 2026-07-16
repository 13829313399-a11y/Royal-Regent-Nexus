import { describe, expect, it, vi } from 'vitest'
import {
  createCustomerPriceArtifactApi,
  type CustomerPriceArtifactHttpClient,
} from '@/api/customerPriceArtifact'

function client() {
  return {
    get: vi.fn(async (url: string) => url.endsWith('/download')
      ? {
          data: new Blob(['p4']),
          headers: {
            'x-internal-quote-release-stage': 'p4_final_approved',
            'x-content-sha256': 'sha-1',
          },
        }
      : { data: [] }),
    post: vi.fn(async () => ({ data: { id: 'handoff-1', status: 'consumed' } })),
  } satisfies CustomerPriceArtifactHttpClient
}

describe('customer-price internal-quote artifact API adapter', () => {
  it('lists factory-scoped handoffs with authoritative status filters', async () => {
    const http = client()
    const api = createCustomerPriceArtifactApi(http)

    await api.list({
      factoryId: 'huaxing',
      status: 'revoked',
      customer: '迪士尼',
      keyword: 'IQ-HX',
    })
    await api.list({ factoryId: 'huaxing', status: 'all' })

    expect(http.get).toHaveBeenNthCalledWith(1, '/customer-price/internal-quote-artifacts', {
      params: {
        factory_id: 'huaxing',
        status: 'revoked',
        customer: '迪士尼',
        keyword: 'IQ-HX',
      },
    })
    expect(http.get).toHaveBeenNthCalledWith(2, '/customer-price/internal-quote-artifacts', {
      params: { factory_id: 'huaxing', status: '' },
    })
  })

  it('uses one-time consume and blob download endpoints', async () => {
    const http = client()
    const api = createCustomerPriceArtifactApi(http)

    await api.consume('handoff-1', 'customer-price-ui:handoff-1')
    const download = await api.download('handoff-1')

    expect(http.post).toHaveBeenCalledWith(
      '/customer-price/internal-quote-artifacts/handoff-1/consume',
      { consumer_reference: 'customer-price-ui:handoff-1' },
    )
    expect(http.get).toHaveBeenLastCalledWith(
      '/customer-price/internal-quote-artifacts/handoff-1/download',
      { responseType: 'blob' },
    )
    expect(download.releaseStage).toBe('p4_final_approved')
    expect(download.sha256).toBe('sha-1')
    expect(download.blob).toBeInstanceOf(Blob)
  })
})
