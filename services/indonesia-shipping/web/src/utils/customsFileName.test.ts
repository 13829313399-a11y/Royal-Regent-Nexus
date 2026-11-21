import { expect, it } from 'vitest'
import { customsFileName } from './customsExport'

it.each(['2026-11-09', '2026-11-09T00:00:00+08:00', '2026-11-09T23:30:00-08:00'])(
  '报关文件名保留装柜业务日期，不随时区换日：%s', loadDate => {
    expect(customsFileName({ loadDate, customer: 'RRI', containerCount: 1, containerNo: 'QA-RRI-1109' }))
      .toBe('11月9日RRI1柜QA-RRI-1109.xlsx')
  },
)

it.each([undefined, '', 'invalid', '2026-02-30'])(
  '缺失或无效装柜日期不编造日期：%s', loadDate => {
    expect(customsFileName({ loadDate })).toBe('未填装柜日期客户1柜.xlsx')
  },
)
