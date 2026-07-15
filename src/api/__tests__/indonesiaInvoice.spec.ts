import { describe, expect, it } from 'vitest'
import { createIndonesiaInvoiceApi } from '@/api/indonesiaInvoice'

describe('indonesiaInvoiceApi', () => {
  it('submits neutral PDF A/B inputs so the server can identify their roles', async () => {
    const calls: Array<{ url: string; data: FormData; config?: unknown }> = []
    const client = {
      async post<T>(url: string, data: FormData, config?: unknown): Promise<{ data: T }> {
        calls.push({ url, data, config })
        return { data: {} as T }
      },
    }
    const api = createIndonesiaInvoiceApi(client as never)
    const invoiceA = new Blob(['supplier invoice'], { type: 'application/pdf' })
    const invoiceB = new Blob(['customer invoice'], { type: 'application/pdf' })

    await api.reconcileRri({ invoiceA, invoiceB })

    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe('/indonesia-invoices/rri/reconcile')
    const submittedInvoiceA = calls[0].data.get('invoice_a')
    const submittedInvoiceB = calls[0].data.get('invoice_b')
    expect(submittedInvoiceA).toBeInstanceOf(Blob)
    expect(submittedInvoiceB).toBeInstanceOf(Blob)
    await expect((submittedInvoiceA as Blob).text()).resolves.toBe('supplier invoice')
    await expect((submittedInvoiceB as Blob).text()).resolves.toBe('customer invoice')
  })
})
