import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { InternalQuoteSection } from '@/types/internalQuoteDesk'
import InternalQuoteSectionRail from '../InternalQuoteSectionRail.vue'

const salesSection: InternalQuoteSection = {
  code: 'sales',
  label: '业务部',
  owner: '业务部',
  status: 'draft',
  isRequired: true,
  revision: 2,
  totalHkd: 0,
  updatedAt: '2026-08-17 16:00:00',
  formulaHint: '',
  dependencies: [],
  warnings: [],
  lines: [],
  attachments: [],
  payload: {},
  calculation: {},
  calculationStatus: 'pending',
  dependencyStatus: 'current',
  filledAt: '',
}

describe('internal quote baseline difference navigation', () => {
  it('marks only departments that differ from the baseline product', () => {
    const wrapper = mount(InternalQuoteSectionRail, {
      props: {
        sections: [salesSection],
        activeCode: 'sales',
        wholeQuoteReview: true,
        differentSectionCodes: ['sales'],
        blockProgress: {
          sales: [{ id: 'testing-fee', title: '测试费部分', requirement: 'optional', status: 'optional', criteria: '可选' }],
        },
      },
    })

    const departmentButton = wrapper.get('.quote-section-entry button')
    expect(departmentButton.classes()).toContain('baseline-different')
    expect(departmentButton.text()).toContain('与基准款不同')
  })
})
