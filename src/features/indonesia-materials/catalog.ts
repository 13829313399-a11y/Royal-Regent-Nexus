import type { MaterialRecord } from '@/api/indonesiaMaterials'

export function fixedCustomers(records: MaterialRecord[], activeOnly = true) {
  return records.filter(row => row.kind === 'customer' && (!activeOnly || row.data.status === 'active'))
    .sort((a, b) => String(a.data.name).localeCompare(String(b.data.name), 'zh-CN'))
}

export function customerOptions(records: MaterialRecord[], historical = '') {
  const options = fixedCustomers(records).map(row => ({ value: String(row.data.name), label: String(row.data.name) }))
  if (historical && !options.some(option => option.value === historical)) options.push({ value: historical, label: `${historical}（历史资料／已停用）` })
  return [{ value: '', label: '请选择当前厂区的固定客人' }, ...options]
}

export function customerProducts(records: MaterialRecord[], customer: string) {
  return records.filter(row => row.kind === 'product' && row.data.customer === customer)
    .sort((a, b) => String(a.data.code).localeCompare(String(b.data.code)))
}
