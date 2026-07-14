import { expect, test } from 'vitest'
import { createMoldingSampleApi } from '../moldingSample.js'
import type { MoldingSampleTrialReportData } from '@/types/moldingSample'

const emptyReportData: MoldingSampleTrialReportData = {
  mold_supplier: '', sample_category: '', material_name: 'HIPS 425', material_shots: '30', material_weight: '', color: '深绿色', color_code: '71139', color_shots: '', color_weight: '', virgin_material_shots: '', virgin_material_weight: '', runner_material_shots: '', runner_material_weight: '', water_ratio: '', water_shots: '', water_material_weight: '', water_weight: '', special_requirements: '', front_mold_water: '', rear_mold_water: '', other_trial_requirement: '', other_trial_requirement_note: '', baking_time_hours: '', mold_condition: '', expected_return_time: '', gross_weight: '', net_weight: '', plastic_model: '', machine_model: '', machine_no: '', cooling_time: '', holding_time: '', cycle_time: '', injection_speed: '', ejector_count: '', cushion_pressure: '', clamping_force: '', high_pressure: '', low_pressure: '', pressure_stage_1: '', pressure_stage_2: '', pressure_stage_3: '', pressure_stage_4: '', barrel_temperature_head: '', barrel_temperature_middle: '', barrel_temperature_end: '', molding_mode: '', mold_issues: [], part_issues: [], issue_notes: '', trial_summary: '', trial_round: '', verdict: '', tester_name: '', tester_date: '', molding_supervisor_name: '', molding_supervisor_date: '', engineer_name: '', engineer_date: '',
}

test('upserts a trial report under the selected order and mold item', async () => {
  const calls: Array<{ url: string, data?: unknown }> = []
  const api = createMoldingSampleApi({
    async get() { return { data: {} } },
    async post() { return { data: {} } },
    async patch() { return { data: {} } },
    async put(url, data) { calls.push({ url, data }); return { data: {} } },
    async delete() { return { data: {} } },
  })

  await api.upsertTrialReport('BP-11', 'BP-11-001', { data: emptyReportData })

  expect(calls).toEqual([{
    url: '/injection/BP-11/trial-reports/BP-11-001',
    data: { data: emptyReportData },
  }])
})
