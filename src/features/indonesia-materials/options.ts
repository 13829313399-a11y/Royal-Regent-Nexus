import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import type { Field } from './forms'
export const optionGroups = [
  { value: 'category', label: '物料类别' }, { value: 'customs_unit', label: '报关单位' },
  { value: 'unit', label: '数量单位' }, { value: 'usage', label: '产品用途' },
  { value: 'currency', label: '币种' }, { value: 'supplier', label: '供应商' }, { value: 'export_company', label: '出口公司' },
]
export function maintainedOptions(records: MaterialRecord[], defaults: Data[], group: string, includeDeleted = false) {
  const values = new Map<string, { data: Data; record?: MaterialRecord }>()
  defaults.filter(item => item.group === group).forEach(data => values.set(data.value, { data }))
  records.filter(row => row.kind === 'option' && row.data.group === group).forEach(record => values.set(record.data.value, { data: record.data, record }))
  return [...values.values()].filter(item => includeDeleted || !item.data.deleted)
}
export function choiceFields(fields: Field[], records: MaterialRecord[], defaults: Data[], historical: Data = {}) {
  return fields.map(field => {
    if (!optionGroups.some(group => group.value === field.key)) return field
    const options = maintainedOptions(records, defaults, field.key).filter(item => item.data.status === 'active').map(item => ({ value: String(item.data.value), label: String(item.data.value) }))
    if (historical[field.key] && !options.some(option => option.value === historical[field.key])) options.push({ value: historical[field.key], label: `${historical[field.key]}（历史值）` })
    return { ...field, type: ['supplier', 'export_company'].includes(field.key) ? 'search' as const : 'select' as const,
      options: [{ value: '', label: '请选择' }, ...options] }
  })
}
