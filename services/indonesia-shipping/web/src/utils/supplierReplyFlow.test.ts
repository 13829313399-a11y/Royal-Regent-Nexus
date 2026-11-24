import { readFileSync } from 'node:fs'
import { createContext, runInContext } from 'node:vm'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'

const source = readFileSync(new URL('../pages/PurchasePage.tsx', import.meta.url), 'utf8')
const tree = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
let handler = ''
function collect(node: ts.Node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'setSupplierReply') handler = node.getText(tree)
  ts.forEachChild(node, collect)
}
collect(tree)
const executable = ts.transpileModule(handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
const row = { id: 1, po_id: 2, material_id: 3, tomy_po: 'PO1', supplier: 'QA', supplier_reply_date: null }

function fixture() {
  const context = createContext({
    supplierReplyPending: { current: new Set<number>() },
    setSupplierReplySavingIds: vi.fn(),
    api: { put: vi.fn(async () => ({})) }, load: vi.fn(async () => []),
    message: { success: vi.fn() },
  })
  runInContext(executable, context)
  return context
}

describe('supplier reply page saves', () => {
  it('coalesces duplicate date/Enter events until the saved row has reloaded', async () => {
    const c = fixture()
    let release!: () => void
    c.load.mockImplementation(() => new Promise<void>(resolve => { release = resolve }))
    const first = c.setSupplierReply(row, '2026-11-19')
    await c.setSupplierReply(row, '2026-11-19')
    expect(c.api.put).toHaveBeenCalledTimes(1)
    expect(c.supplierReplyPending.current.has(1)).toBe(true)
    release()
    await first
    expect(c.supplierReplyPending.current.size).toBe(0)
    expect(c.message.success).toHaveBeenCalledTimes(1)
  })

  it('does not save the same date or repeatedly clear an empty reply', async () => {
    const c = fixture()
    await c.setSupplierReply(row, null)
    await c.setSupplierReply({ ...row, supplier_reply_date: '2026-11-19' }, '2026-11-19')
    expect(c.api.put).not.toHaveBeenCalled()
  })

  it('releases the saving lock after a reload failure and preserves the conflict baseline on retry', async () => {
    const c = fixture()
    c.load.mockRejectedValueOnce(new Error('offline'))
    await expect(c.setSupplierReply(row, '2026-11-19')).rejects.toThrow('offline')
    expect(c.supplierReplyPending.current.size).toBe(0)
    await c.setSupplierReply(row, '2026-11-19')
    expect(c.api.put).toHaveBeenLastCalledWith('/purchase/items/1/supplier-reply', {
      po_id: 2, material_id: 3, tomy_po: 'PO1', supplier: 'QA', expected_date: null, reply_date: '2026-11-19',
    })
  })
})
