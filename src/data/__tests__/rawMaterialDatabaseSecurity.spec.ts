import { describe, expect, it } from 'vitest'
import { rawMaterialDatabaseRows } from '@/data/rawMaterialDatabase'

describe('raw material browser data security', () => {
  it('does not bundle positive unit prices or other costs', () => {
    const exposedRows = rawMaterialDatabaseRows.filter((row) =>
      (row.unitPriceHkdPerLb ?? 0) > 0 || (row.otherCostHkdPerLb ?? 0) > 0,
    )

    expect(exposedRows).toEqual([])
  })
})
