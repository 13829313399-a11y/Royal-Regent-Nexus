import { describe, expect, it, vi } from 'vitest'
import { createCustomerOrderScheduleApi } from '@/api/customerOrderSchedule'

describe('customer order schedule api', () => {
  it('requests factory-scoped customers and all three independently paged sections', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { factory_id: 'huaxing', items: [{ code: 'buzzbee', name: 'BuzzBee' }] } })
      .mockResolvedValueOnce({ data: { factory_id: 'huaxing', customer_code: 'buzzbee' } })
    const api = createCustomerOrderScheduleApi({ get })

    await api.customers('huaxing')
    await api.get('huaxing', {
      customerCode: 'buzzbee', q: 'PO 0007', dateFrom: '2026-10-01', dateTo: '2026-10-31',
      unshippedPage: 2, shippedPage: 3, cancelledPage: 4,
    })

    expect(get).toHaveBeenNthCalledWith(1, '/customer-order-ledger/schedule/customers?factory_id=huaxing')
    expect(get).toHaveBeenNthCalledWith(2, expect.stringContaining('/customer-order-ledger/schedule?'))
    const url = get.mock.calls[1]![0] as string
    expect(url).toContain('factory_id=huaxing')
    expect(url).toContain('customer_code=buzzbee')
    expect(url).toContain('q=PO+0007')
    expect(url).toContain('date_from=2026-10-01')
    expect(url).toContain('date_to=2026-10-31')
    expect(url).toContain('unshipped_page=2')
    expect(url).toContain('shipped_page=3')
    expect(url).toContain('cancelled_page=4')
    expect(url).toContain('page_size=50')
  })
})
