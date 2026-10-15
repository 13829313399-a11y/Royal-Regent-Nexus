import { describe, expect, it } from 'vitest'
import { groupStorageKey, groupSubmission, newOrderGroup, newGroupStyle, readGroups, saveGroups } from '../orderGroups'

describe('incomplete multi-PO drafts', () => {
  it('starts with one style, permits incomplete storage and separates user/epoch/factory', () => {
    const group = newOrderGroup('inch')
    expect(group.rows).toHaveLength(1)
    expect(new Set(group.rows.map(row => row.id)).size).toBe(1)
    group.rows[0]!.customer_po = '00001'; group.rows[0]!.source = '客户原表.xlsx / Sheet1 / 5'
    const map = new Map<string, string>(), storage = { setItem: (k: string, v: string) => { map.set(k, v) }, getItem: (k: string) => map.get(k) ?? null }
    const key = groupStorageKey('U', 1, 'huaxing'); saveGroups(storage, key, [group])
    expect(readGroups(storage, key)[0]!.rows[0]!.source).toContain('Sheet1')
    expect(readGroups(storage, groupStorageKey('U', 2, 'huaxing'))).toEqual([])
    expect(readGroups(storage, groupStorageKey('U', 1, 'huakang-a'))).toEqual([])
    expect(() => groupSubmission(group, 'huaxing', '客户')).toThrow('组名、客户')
  })
  it.each([2, 6])('keeps %i PO rows and paper quantities separate and requires all rows before conversion', count => {
    const group = newOrderGroup('inch'); group.customer_code = 'CUSTOMER'
    while (group.rows.length < count) group.rows.push(newGroupStyle('inch'))
    group.rows.forEach((row, index) => {
      Object.assign(row, { customer_po: `00${index}`, contract_no: 'C-1', item_no: `I-${index}`, customer_due_date: '2026-11-01', source: `原表第${index + 1}行` })
      Object.assign(row.lines[0]!, { packaging_type: '平卡', paper_quality: 'B33', specification: '10*20', unit: '张', required_quantity: String(index + 1) })
    })
    group.rows[count - 1]!.item_no = ''
    expect(() => groupSubmission(group, 'huaxing', '客户')).toThrow(`第 ${count} 款`)
    group.rows[count - 1]!.item_no = `I-${count - 1}`
    const request = groupSubmission(group, 'huaxing', '客户')
    expect(request.rows.map(row => row.order.lines[0]!.required_quantity)).toEqual(Array.from({ length: count }, (_, index) => index + 1))
    expect(request.rows[0]!.order.customer_po).toBe('000')
    expect(request.rows[0]!.order.lines[0]!.dimension_unit).toBe('inch')
    expect(request.rows[count - 1]!.source).toBe(`原表第${count}行`)
  })
  it('refuses corrupted stored drafts instead of replacing their data', () => {
    expect(() => readGroups({ getItem: () => '[{"id":"old"}]' }, 'k')).toThrow('已保留原数据')
  })
})
