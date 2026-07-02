import assert from 'node:assert/strict'
import { moldingSampleFactoryRecords } from '../moldingSampleWorkflowMock.js'

const huakangARecord = moldingSampleFactoryRecords['huakang-a']

assert.deepEqual(
  huakangARecord.items.map((item) => ({
    id: item.id,
    receipt_no: item.receipt_no,
    collected_weight_kg: item.collected_weight_kg,
    actual_weight_kg: item.actual_weight_kg,
    actual_amount_hkd: item.actual_amount_hkd,
    injection_cost: item.injection_cost,
    injection_cost_hkd: item.injection_cost_hkd,
    exchange_rate_at_save: item.exchange_rate_at_save,
  })),
  [
    {
      id: 'BP-62437-001',
      receipt_no: '',
      collected_weight_kg: null,
      actual_weight_kg: null,
      actual_amount_hkd: null,
      injection_cost: null,
      injection_cost_hkd: null,
      exchange_rate_at_save: null,
    },
    {
      id: 'BP-62437-002',
      receipt_no: '',
      collected_weight_kg: null,
      actual_weight_kg: null,
      actual_amount_hkd: null,
      injection_cost: null,
      injection_cost_hkd: null,
      exchange_rate_at_save: null,
    },
    {
      id: 'BP-62437-003',
      receipt_no: '',
      collected_weight_kg: null,
      actual_weight_kg: null,
      actual_amount_hkd: null,
      injection_cost: null,
      injection_cost_hkd: null,
      exchange_rate_at_save: null,
    },
  ],
)
