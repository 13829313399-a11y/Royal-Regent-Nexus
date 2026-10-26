import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import Component from '../CartonScheduleCoverageSummary.vue'
import type { CartonImportBatchResponse } from '@/api/cartonProcurement'

const batch = (): CartonImportBatchResponse => ({ id: 'B1', factory_id: 'huaxing', import_type: 'WEEKLY_SCHEDULE', original_filename: '排期.xlsx', source_sha256: 'a', import_profile: '', content_type: '', source_size_bytes: 1, status: 'CONFIRMED', imported_by: 'U1', imported_by_name: '用户', created_at: '2026-10-20', parse_summary: {}, duplicate: false })
it('does not reinterpret old batches as full and exposes exact excluded row/date evidence without merging duplicates', () => {
  const old = mount(Component, { props: { batch: batch() } })
  expect(old.text()).toContain('历史未声明覆盖范围，不补标全量'); old.unmount()
  const row = batch()
  row.parse_summary.schedule_coverage = { version: 1, scope_mode: 'FULL', as_of_date: '2026-10-01', coverage_start: '2026-10-01', coverage_end: '2026-10-31', date_basis: 'CUSTOMER_DUE_DATE', full_scope_confirmed: true, identity_profile: { version: 1 }, excluded_rows: [{ source_sheet: 'ITEM2', source_row: 9, contract_no: 'SC1', item_no: 'I1', source_customer_due_date: '10月底分批', reason: '缺少完整客户交期' }], missing_rows: [1] }
  row.parse_summary.rows = [{ schedule_identity_duplicate: true }, { schedule_identity_duplicate: true }]
  const w = mount(Component, { props: { batch: row } })
  expect(w.text()).toContain('排期版本 2026-10-01'); expect(w.text()).toContain('上传 2026-10-20')
  expect(w.text()).toContain('重复身份相关 2 行'); expect(w.text()).toContain('第 9 行'); expect(w.text()).toContain('10月底分批'); expect(w.text()).toContain('缺少完整客户交期')
  w.unmount()
})
