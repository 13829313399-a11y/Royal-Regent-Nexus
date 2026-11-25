import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as XLSX from 'xlsx-js-style'
import { exportMpo } from './moldingPoExport'
import { productionFactories } from '../deployment'
import { validateExportSession } from '../auth/validateExportSession'

vi.mock('xlsx-js-style', async importOriginal => {
  const original = await importOriginal<{ default: typeof XLSX }>()
  return { ...original.default, writeFile: vi.fn() }
})
vi.mock('../auth/validateExportSession', () => ({ validateExportSession: vi.fn() }))

describe('production orders for Nexus factories', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(validateExportSession).mockResolvedValue(true)
  })

  it.each(productionFactories)('exports sewing quantities, currencies and the assigned factory %s', async workshop => {
    await exportMpo({ category: '车缝', no: 'S1', workshop, customer: 'Test', currency: '¥', items: [
      { partCode: 'P1', partName: '面片', qty: 12, unitPrice: 0.5 },
      { partCode: 'P2', partName: '底片', qty: 6, currency: 'HK$' },
    ] })
    const [book, name] = vi.mocked(XLSX.writeFile).mock.calls[0]
    const sheet = XLSX.read(XLSX.write(book, { type: 'buffer', bookType: 'xlsx' })).Sheets['车缝生产单']
    expect(name).toBe('S1_车缝生产单.xlsx')
    expect(sheet.B2.v).toBe(workshop)
    expect(sheet.D2.v).toBe('S1')
    expect(sheet.B5.v).toBe('P1')
    expect(sheet.F5.v).toBe(12)
    expect(sheet.I5.f).toContain('F5*H5')
    expect([sheet.G7.v, sheet.G8.v]).toEqual(['¥', 'HK$'])
    expect(sheet.I7.f).toContain('SUMIF(G5:G6,G7,I5:I6)')
    expect(sheet.I7.v).toBe(6)
    expect(sheet.I8.v).toBe('待录价')
    expect(XLSX.utils.sheet_to_csv(sheet)).not.toMatch(/东莞|兴信|啤数/)
  })

  it.each(['塑胶', '搪胶'])('uses the current factory on the existing %s form', async category => {
    await exportMpo({ category, workshop: '华兴', no: 'M1', items: [{ qty: 3 }] })
    const [book] = vi.mocked(XLSX.writeFile).mock.calls[0]
    const sheet = book.Sheets[book.SheetNames[0]]
    expect(sheet.A1.v).toBe('华兴')
    expect(XLSX.utils.sheet_to_csv(sheet)).not.toMatch(/东莞|兴信|D栋3楼|B车间C栋/)
  })

  it('checks the active session before writing a sewing workbook', async () => {
    vi.mocked(validateExportSession).mockResolvedValue(false)
    await exportMpo({ category: '车缝', workshop: '华兴', items: [] })
    expect(XLSX.writeFile).not.toHaveBeenCalled()
  })
})
