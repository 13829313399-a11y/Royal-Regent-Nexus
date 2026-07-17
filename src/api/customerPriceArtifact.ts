import { http } from '@/lib/http'

type ArtifactResponseHeaders = Record<string, unknown> & {
  get?: (name: string) => unknown
}

export interface CustomerPriceArtifactHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T; headers?: ArtifactResponseHeaders }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T; headers?: ArtifactResponseHeaders }>
}

export type CustomerPriceArtifactStatus = 'available' | 'consumed' | 'revoked'
export type CustomerPriceArtifactStatusFilter = CustomerPriceArtifactStatus | 'all'

export interface CustomerPriceInternalQuoteArtifact {
  id: string
  quote_id: string
  export_id: string
  factory_id: string
  customer: string
  quote_no: string
  version_label: string
  release_revision: number
  status: CustomerPriceArtifactStatus
  artifact_manifest: Record<string, unknown>
  file_name: string
  content_type: string
  size_bytes: number
  sha256: string
  created_by: string
  created_by_name: string
  created_at: string
  consumed_by: string
  consumed_by_name: string
  consumed_at: string
  consumer_reference: string
  revoked_at: string
  revoke_reason: string
}

export interface CustomerPriceArtifactListOptions {
  factoryId: string
  status?: CustomerPriceArtifactStatusFilter
  customer?: string
  keyword?: string
}

export interface CustomerPriceArtifactDownload {
  blob: Blob
  releaseStage: string
  sha256: string
}

function readHeader(headers: ArtifactResponseHeaders | undefined, name: string) {
  const fromGetter = headers?.get?.(name)
  if (fromGetter !== undefined && fromGetter !== null) {
    return String(fromGetter)
  }

  const matched = Object.entries(headers ?? {}).find(([key]) => key.toLowerCase() === name.toLowerCase())
  return matched?.[1] === undefined || matched[1] === null ? '' : String(matched[1])
}

export function createCustomerPriceArtifactApi(client: CustomerPriceArtifactHttpClient = http) {
  return {
    async list(options: CustomerPriceArtifactListOptions) {
      const response = await client.get<CustomerPriceInternalQuoteArtifact[]>(
        '/customer-price/internal-quote-artifacts',
        {
          params: {
            factory_id: options.factoryId,
            status: options.status === 'all' ? '' : (options.status ?? 'available'),
            ...(options.customer ? { customer: options.customer } : {}),
            ...(options.keyword ? { keyword: options.keyword } : {}),
          },
        },
      )
      return response.data
    },
    async consume(handoffId: string, consumerReference: string) {
      const response = await client.post<CustomerPriceInternalQuoteArtifact>(
        `/customer-price/internal-quote-artifacts/${handoffId}/consume`,
        { consumer_reference: consumerReference },
      )
      return response.data
    },
    async download(handoffId: string): Promise<CustomerPriceArtifactDownload> {
      const response = await client.get<Blob>(
        `/customer-price/internal-quote-artifacts/${handoffId}/download`,
        { responseType: 'blob' },
      )
      return {
        blob: response.data,
        releaseStage: readHeader(response.headers, 'x-internal-quote-release-stage'),
        sha256: readHeader(response.headers, 'x-content-sha256'),
      }
    },
  }
}

export const customerPriceArtifactApi = createCustomerPriceArtifactApi()
