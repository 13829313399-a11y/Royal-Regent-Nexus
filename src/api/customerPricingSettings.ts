import { http } from '@/lib/http'
import type { CustomerPricingSettings } from '@/lib/customerPriceConverters/pricingSettings'

export const customerPricingSettingsApi = {
  async get(factoryId: string, customerId: string): Promise<CustomerPricingSettings> {
    return (await http.get('/customer-price/settings', { params: { factory_id: factoryId, customer_id: customerId } })).data
  },
  async save(settings: CustomerPricingSettings): Promise<CustomerPricingSettings> {
    return (await http.put('/customer-price/settings', { revision: settings.revision, materials: settings.materials, rates: settings.rates, texts: settings.texts }, { params: { factory_id: settings.factory_id, customer_id: settings.customer_id } })).data
  },
  async snapshot(factoryId: string, customerId: string): Promise<CustomerPricingSettings> {
    const settings = await this.get(factoryId, customerId)
    return (await http.post('/customer-price/settings/snapshots', { revision: settings.revision }, { params: { factory_id: factoryId, customer_id: customerId } })).data
  },
}
