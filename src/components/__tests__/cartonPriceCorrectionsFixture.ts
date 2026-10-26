import type { PriceCorrectionDetail, PriceCorrectionImpact, PriceCorrectionsWorkspace } from '@/api/cartonPriceCorrections'

export function correctionImpact(overrides: Partial<PriceCorrectionImpact> = {}): PriceCorrectionImpact {
  return { impact_fingerprint: 'i'.repeat(64), can_apply: true, blockers: [], summary: { currency: 'CNY', source_cost_difference: '10.000000', inbound_cost_difference: '10.000000', outbound_cost_difference: '6.000000', other_cost_difference: '0', ending_cost_difference: '4.000000', bridge_difference: '0', payable_difference: '10.00' },
    movements: [{ movement_id: 'ISSUE1', document_no: '领料-001', movement_type: 'OUTBOUND', issue_kind: 'ORDER_ISSUE', source_type: 'ORDER', occurred_at: '2026-09-12T09:00:00+08:00', quantity: '-6', unit: '个', currency: 'CNY', customer_name: '客户', contract_no: 'C1', item_no: 'BOX1', old_cost_amount: '-12.000000', new_cost_amount: '-18.000000', cost_difference: '-6.000000' }],
    pools: [{ id: 'POOL1', customer_code: 'CUSTOMER1', currency: 'CNY', unit: '个', quantity: '4', old_amount: '8', new_amount: '12', difference: '4' }],
    closings: [{ id: 'CLOSE1', period: '2026-09', customer_code: 'CUSTOMER1', currency: 'CNY', status: 'DRAFT', revision: 2, old_ending_amount: '8', new_ending_amount: '12', amount_difference: '4' }], ...overrides }
}
export function correctionRow(overrides: Partial<PriceCorrectionDetail> = {}): PriceCorrectionDetail {
  return { receipt_line_id: 'LINE1', receipt_id: 'RECEIPT1', movement_id: 'INBOUND1', factory_id: 'huaxing', supplier_id: 'SUP1', currency: 'CNY', quantity: '10', unit: '个', document_no: '送货-001', acceptance_date: '2026-09-10', customer_name: '客户', contract_no: 'C1', item_no: 'BOX1', packaging_type: '外箱', paper_quality: 'A33', specification: '30*20*10',
    revision: 2, source_fingerprint: 's'.repeat(64), status: 'SUPPLIER_CONFIRMED', can_propose: true, allowed_actions: ['PROPOSE', 'WITHDRAW', 'FINAL_CONFIRM'], raw_unit_price: '2', current_cost_unit_price: '2', current_unit_price: '2', original_supplier_unit_price: '2.1', proposed_unit_price: '3',
    proposal: { id: 'PROPOSAL1', version: 1, status: 'SUPPLIER_CONFIRMED', proposed_unit_price: '3', free_confirmed: false, document_no: '报价-新1', document_date: '2026-10-20', reason: '原报价录入错误', source_fingerprint: 's'.repeat(64), created_at: '2026-10-20T09:00:00+08:00', created_by: '仓管', supplier_review: { decision: 'CONFIRMED', by: '供应商', at: '2026-10-20T10:00:00+08:00', reason: '核对确切批次报价' } },
    history: [{ id: 'H1', action: 'PROPOSE', actor_name: '仓管', created_at: '2026-10-20T09:00:00+08:00', reason: '原报价录入错误', data: {} }], blockers: [], ...overrides }
}
export function correctionWorkspace(row = correctionRow()): PriceCorrectionsWorkspace { return { items: [row], total: 1, limit: 25, offset: 0, pending_count: 1 } }
