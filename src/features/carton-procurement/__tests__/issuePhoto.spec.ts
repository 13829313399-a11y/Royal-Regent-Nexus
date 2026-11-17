import { describe, expect, it } from 'vitest'
import { issuePhotoMatches } from '../issuePhoto'

const stock = [
  { id: 'first', poNumber: 'RL-449995-69', itemNo: '1423020051', balance: 10 },
  { id: 'other-bin', poNumber: 'RL-449995-69', itemNo: '1423020051', balance: 6 },
  { id: 'empty-bin', poNumber: 'RL-449995-69', itemNo: '1423020051', balance: 0 },
  { id: 'next-order', poNumber: 'RL-449995-70', itemNo: '1423020051', balance: 5 },
]

describe('issue-photo candidates', () => {
  it('lists each available position for an exact match and uses the chosen order for a handwritten suffix', () => {
    expect(issuePhotoMatches({ contract_no: 'RL-449995-69', item_no: '1423020051', evidence: '' }, stock)
      .map(result => result.position.id)).toEqual(['first', 'other-bin'])
    expect(issuePhotoMatches({ contract_no: '-70', item_no: '', evidence: '-70' }, stock, 'RL-449995-69', '1423020051')
      .map(result => result.position.id)).toEqual(['next-order'])
  })

  it('offers glued or OCR-confused text for review and leaves unknown rows unmatched', () => {
    expect(issuePhotoMatches({ contract_no: '', item_no: '', evidence: 'R1-449995-69 1.423020051' }, stock)
      .map(result => result.position.id)).toEqual(['first', 'other-bin'])
    expect(issuePhotoMatches({ contract_no: '', item_no: '', evidence: '防撞卡' }, stock)).toEqual([])
  })

  it('keeps contract and customer PO separate and shows both exact candidates for a bare PO', () => {
    const positions = [
      { ...stock[0], poNumber: '000123', customerPo: '456' },
      { ...stock[1], poNumber: '789', customerPo: '000123' },
      { ...stock[3], poNumber: '789', customerPo: '123' },
    ]
    const row = { contract_no: '000123', item_no: '1423020051', evidence: '' }
    const find = (reference_kind: 'contract' | 'customer_po' | 'po') =>
      issuePhotoMatches({ ...row, reference_kind }, positions).map(({ position, label }) => [position.id, label])
    expect(find('contract')).toEqual([['first', '合同和货号匹配']])
    expect(find('customer_po')).toEqual([['other-bin', '客户 PO 和货号匹配']])
    expect(find('po')).toEqual([['first', '合同和货号匹配'], ['other-bin', '客户 PO 和货号匹配']])
  })

  it('uses the separate PO to distinguish orders that share a contract and item', () => {
    const positions = [
      { ...stock[0], customerPo: 'PO-01' },
      { ...stock[1], customerPo: 'PO-02' },
    ]
    expect(issuePhotoMatches({
      contract_no: 'RL-449995-69', customer_po: 'PO-02', item_no: '1423020051', evidence: '',
    }, positions).map(({ position, label }) => [position.id, label])).toEqual([
      ['other-bin', '合同、客户 PO 和货号匹配'],
    ])
  })

  it('uses an exact stock code to constrain a one-character OCR error', () => {
    const row = { contract_no: 'RL-449995-69', item_no: '1423020057', evidence: '' }
    expect(issuePhotoMatches(row, stock).map(({ position, score }) => [position.id, score])).toEqual([
      ['first', 4], ['other-bin', 4],
    ])
  })

  it('suggests visible codes without headers and allows a short manual fragment', () => {
    const row = { contract_no: '', item_no: '', evidence: 'RL-449995-69 · 1423020051' }
    expect(issuePhotoMatches(row, stock).map(({ position }) => position.id)).toEqual(['first', 'other-bin'])
    const fragment = { ...row, contract_no: '995-70', evidence: '' }
    expect(issuePhotoMatches(fragment, stock)).toEqual([])
    expect(issuePhotoMatches(fragment, stock, '', '', true).map(({ position }) => position.id)).toEqual(['next-order'])
  })
})
