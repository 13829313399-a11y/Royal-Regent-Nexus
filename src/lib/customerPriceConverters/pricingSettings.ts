import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'

export interface CustomerMaterialPrice {
  material: string
  price: number
  currency: 'HKD' | 'USD'
  unit: 'kg' | 'lb'
}
export interface CustomerRateDefinition {
  label: string
  kind: 'multiplier' | 'rate' | 'price' | 'exchange'
  description?: string | null
}
export interface CustomerPricingSettings {
  factory_id: string
  customer_id: string
  revision: number
  materials: CustomerMaterialPrice[]
  rates: Record<string, number>
  texts: Record<string, string>
  rate_definitions?: Record<string, CustomerRateDefinition>
  text_definitions?: Record<string, { label: string }>
  updated_at: string
  updated_by_name: string
  snapshot_id?: string
  snapshot_ids?: string[]
}

export function pricingRate(settings: CustomerPricingSettings | undefined, key: string, legacy: number): number {
  if (!settings) return legacy
  const value = settings.rates[key]
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error(`客户基础信息缺少有效参数：${key}`)
  return value
}
export function pricingMaterial(settings: CustomerPricingSettings | undefined, material: string, currency: 'HKD' | 'USD', unit: 'kg' | 'lb', legacy: number | null): number | null {
  if (!settings) return legacy
  const row = settings.materials.find(r => r.material.trim().toUpperCase() === material.trim().toUpperCase() && r.currency === currency && r.unit === unit)
  if (!row) return null
  if (!Number.isFinite(row.price) || row.price < 0) throw new Error(`客户料价无效：${material}`)
  return row.price
}
export function assertPricingCustomer(settings: CustomerPricingSettings | undefined, customer: string) {
  if (!settings) return
  const factory = customer === 'three-sixty' ? 'huakang-a' : 'huaxing'
  if (settings.customer_id !== customer || settings.factory_id !== factory) throw new Error('客户基础信息与当前客户、厂区不一致')
}

/** Customer workbooks carry only an opaque audit reference, never private rate tables. */
export function stampPricingReference(workbook: Uint8Array, settings?: CustomerPricingSettings): Uint8Array {
  if (!settings?.snapshot_id) return workbook
  const escape = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;')
  const zip = unzipSync(workbook)
  const path = 'docProps/custom.xml'
  let xml = zip[path] ? strFromU8(zip[path]) : '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"></Properties>'
  xml = xml.replace(/<property\b[^>]*name="CustomerPricingReference"[^>]*>[\s\S]*?<\/property>/g, '')
  const pids = Array.from(xml.matchAll(/\bpid="(\d+)"/g), m => Number(m[1]))
  const references = settings.snapshot_ids?.length ? [...new Set(settings.snapshot_ids)].join(',') : settings.snapshot_id
  xml = xml.replace('</Properties>', `<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="${Math.max(1, ...pids) + 1}" name="CustomerPricingReference"><vt:lpwstr>${escape(references)}</vt:lpwstr></property></Properties>`)
  zip[path] = strToU8(xml)
  const content = strFromU8(zip['[Content_Types].xml']!)
  if (!content.includes('/docProps/custom.xml')) zip['[Content_Types].xml'] = strToU8(content.replace('</Types>', '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/></Types>'))
  const rels = strFromU8(zip['_rels/.rels']!)
  if (!rels.includes('custom-properties')) zip['_rels/.rels'] = strToU8(rels.replace('</Relationships>', '<Relationship Id="rIdCustomerPricing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/></Relationships>'))
  return zipSync(zip)
}
