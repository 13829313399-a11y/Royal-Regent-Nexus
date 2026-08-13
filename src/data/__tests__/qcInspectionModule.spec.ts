import { describe, expect, it } from 'vitest'
import {
  departmentModuleRegistry,
  moduleDepartmentIds,
  qcCartonMarkVerificationModule,
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

  it('exposes carton-mark photo verification from the canonical QC department center', () => {
    expect(departmentModuleRegistry.qc.modules).toContain(qcCartonMarkVerificationModule)
    expect(qcCartonMarkVerificationModule.route).toBe('/modules/qc/carton-mark-check')
    expect(qcCartonMarkVerificationModule.owner).toContain('QC')
    expect(departmentModuleRegistry.qa.modules).not.toContain(qcCartonMarkVerificationModule)
  })

  it('offers QC-specific position suggestions', () => {
    expect(getPositionSuggestions('qc')).toContain('QC 检验员')
    expect(getPositionSuggestions('qc')).toContain('QC 主管')
    expect(getPositionSuggestions('qc')).toContain('QC 经理')
  })
})
