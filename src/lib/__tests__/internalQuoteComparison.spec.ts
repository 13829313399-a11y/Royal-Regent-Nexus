import { describe, expect, it } from 'vitest'
import { buildInternalQuoteComparison } from '@/lib/internalQuoteComparison'
import type { InternalQuote, InternalQuoteSection, InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

function section(
  code: InternalQuoteSectionCode,
  totalHkd: number,
  options: Partial<InternalQuoteSection> = {},
): InternalQuoteSection {
  return {
    code,
    label: code,
    owner: '',
    status: 'approved',
    isRequired: true,
    revision: 1,
    totalHkd,
    updatedAt: '',
    formulaHint: '',
    dependencies: [],
    warnings: [],
    lines: [],
    attachments: [],
    payload: {},
    calculation: {},
    calculationStatus: 'valid',
    dependencyStatus: 'current',
    ...options,
  }
}

function quote(id: string, factoryPriceHkd: number, sections: InternalQuoteSection[]): InternalQuote {
  return {
    id,
    quoteNo: `IQ-${id}`,
    productName: `${id}产品`,
    customer: '客户',
    versionLabel: 'V1',
    factoryId: 'huaxing',
    factoryName: '华兴',
    workshopCode: 'huaxing',
    workshopName: '华兴',
    initiatorDepartment: 'sales-business',
    createdById: 'creator',
    initiatorName: '创建人',
    businessOwnerId: 'owner',
    businessOwner: '主管',
    targetCustomerPrice: '无',
    quantity: 100,
    targetDate: '',
    remark: '',
    createdAt: '',
    updatedAt: '',
    status: 'fully_approved',
    fxRmbHkd: 1,
    fxHkdUsd: 1,
    fxRmbUsd: 1,
    referenceSnapshotId: '',
    referenceSnapshot: {},
    formulaVersion: '',
    headerRevision: 1,
    finalReleaseStatus: '',
    factoryPriceHkd,
    summaryComponents: {},
    summaryWarnings: [],
    shippingScenarios: [],
    rr2CostSummary: {} as InternalQuote['rr2CostSummary'],
    sections,
    activities: [],
    comments: [],
    viewRecords: [],
    exports: [],
  }
}

describe('internal quote comparison', () => {
  it('uses the first selected quote as baseline and calculates department gaps', () => {
    const result = buildInternalQuoteComparison([
      quote('A', 10, [section('sales', 2), section('engineering', 3)]),
      quote('B', 13.5, [section('sales', 2.75), section('engineering', 4.5)]),
      quote('C', 8, [section('sales', 1.5), section('engineering', 2.5)]),
    ])

    expect(result.baselineQuoteId).toBe('A')
    expect(result.rows.find((row) => row.code === 'sales')).toMatchObject({
      minimumHkd: 1.5,
      maximumHkd: 2.75,
      gapHkd: 1.25,
      values: [
        { quoteId: 'A', amountHkd: 2, deltaFromBaselineHkd: 0 },
        { quoteId: 'B', amountHkd: 2.75, deltaFromBaselineHkd: .75 },
        { quoteId: 'C', amountHkd: 1.5, deltaFromBaselineHkd: -.5 },
      ],
    })
    expect(result.rows.find((row) => row.code === 'engineering')).toMatchObject({
      minimumHkd: 2.5,
      maximumHkd: 4.5,
      gapHkd: 2,
    })
  })

  it('distinguishes non-participating, not-applicable and invalid sections from zero cost', () => {
    const result = buildInternalQuoteComparison([
      quote('A', 10, [section('sales', 2), section('painting', 0, { status: 'not_applicable' })]),
      quote('B', 11, [section('sales', 4), section('painting', 9, { calculationStatus: 'stale' })]),
      quote('C', 12, [section('sales', 3), section('painting', 8, { isRequired: false })]),
    ])
    const painting = result.rows.find((row) => row.code === 'painting')!

    expect(painting.values).toMatchObject([
      { state: 'not_applicable', amountHkd: 0, deltaFromBaselineHkd: 0 },
      { state: 'invalid', amountHkd: null, deltaFromBaselineHkd: null },
      { state: 'not_participating', amountHkd: null, deltaFromBaselineHkd: null },
    ])
    expect(painting.gapHkd).toBeNull()
  })

  it('does not compare an amount whose upstream dependency is stale', () => {
    const result = buildInternalQuoteComparison([
      quote('A', 10, [section('assembly', 3)]),
      quote('B', 11, [section('assembly', 8, { dependencyStatus: 'stale' })]),
    ])
    const assembly = result.rows.find((row) => row.code === 'assembly')!

    expect(assembly.values).toMatchObject([
      { state: 'valid', amountHkd: 3 },
      { state: 'invalid', amountHkd: null },
    ])
    expect(assembly.gapHkd).toBeNull()
  })
})
