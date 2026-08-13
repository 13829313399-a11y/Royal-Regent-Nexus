import { describe, expect, it } from 'vitest'
import {
  departmentModuleRegistry,
  moduleDepartmentIds,
  qcInspectionOperationsModule,
} from '@/data/enterpriseMock'
import { getPositionSuggestions } from '@/data/positionCatalog'

describe('QC inspection module registry', () => {
  it('registers a formal QC department center and a shared QA entry to the same QC-owned route', () => {
    expect(moduleDepartmentIds).toContain('qc')
    expect(departmentModuleRegistry.qc.modules).toContain(qcInspectionOperationsModule)
    expect(departmentModuleRegistry.qa.modules).toContain(qcInspectionOperationsModule)
    expect(qcInspectionOperationsModule.route).toBe('/modules/qc/inspection-operations')
    expect(qcInspectionOperationsModule.owner).toContain('QC 部')
  })

  it('offers QC-specific position suggestions', () => {
    expect(getPositionSuggestions('qc')).toContain('QC 检验员')
    expect(getPositionSuggestions('qc')).toContain('QC 主管')
    expect(getPositionSuggestions('qc')).toContain('QC 经理')
  })
})
