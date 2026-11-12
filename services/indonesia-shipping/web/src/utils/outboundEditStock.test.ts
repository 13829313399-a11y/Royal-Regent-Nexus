import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'
import { expect, it } from 'vitest'

const page = ts.createSourceFile('OutboundPage.tsx', readFileSync(new URL('../pages/OutboundPage.tsx', import.meta.url), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
let selectedStock = ''
function collect(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(page) === 'selectedStock') selectedStock = node.initializer!.getText(page)
  ts.forEachChild(node, collect)
}
collect(page)
const code = ts.transpileModule(`result = ${selectedStock}`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
const original = { id: 1, po_item_id: 10, qty: 50, received_qty: 125, total_out: 50, available_qty: 75 }
const stocks = [original, { po_item_id: 20, received_qty: 20, total_out: 5, available_qty: 15 }]
function calculate(qty: number, item = 10, stockRows = stocks, creating = false) {
  const ctx = { result: undefined, rows: [original], stockRows, creating, editing: { ...original, po_item_id: item, qty }, useMemo: (fn: () => unknown) => fn() }
  runInNewContext(code, ctx)
  return ctx.result
}
it.each([1, 49, 50, 100, 125])('修改数量为 %s 不改变该记录实际可用库存', qty => {
  expect(calculate(qty)).toMatchObject({ total_out: 0, available_qty: 125 })
})
it('切换物料不能把原物料的出库数量加到新物料库存', () => {
  expect(calculate(10, 20)).toMatchObject({ total_out: 5, available_qty: 15 })
})
it('已出完物料的编辑仍使用原已保存数量', () => {
  expect(calculate(49, 10, [])).toMatchObject({ total_out: 0, available_qty: 125 })
})
it('新增出库不回加任何数量', () => {
  expect(calculate(10, 10, stocks, true)).toMatchObject({ total_out: 50, available_qty: 75 })
})
