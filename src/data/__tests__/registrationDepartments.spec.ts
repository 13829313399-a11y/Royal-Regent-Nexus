import { describe, expect, it } from 'vitest'
import {
  registrationDepartmentLabel,
  registrationDepartments,
} from '../registrationDepartments'

describe('registration department catalog', () => {
  it('keeps the nine registration departments independent from permission positions', () => {
    expect(registrationDepartments.map(({ id, name }) => ({ id, name }))).toEqual([
      { id: 'management', name: '总务' },
      { id: 'engineering', name: '工程部' },
      { id: 'sales-business', name: '业务部' },
      { id: 'production', name: '生产部（啤喷装）' },
      { id: 'three-d-printing', name: '3D打印部' },
      { id: 'pmc-warehouse', name: '仓库' },
      { id: 'qa', name: 'QA部' },
      { id: 'qc', name: 'QC部' },
      { id: 'carton', name: '纸箱部' },
    ])
    expect(registrationDepartmentLabel('engineering')).toBe('工程部')
    expect(registrationDepartmentLabel('future-department')).toBe('future-department')
  })
})
