import { readFileSync } from 'node:fs'
import ts from 'typescript'
import dayjs from 'dayjs'
import { expect, it, vi } from 'vitest'
import { productionFactories } from '../deployment'

const page = ts.createSourceFile('MoldingPosPage.tsx', readFileSync(new URL('./MoldingPosPage.tsx', import.meta.url), 'utf8'),
  ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const handlers = new Set(['priceKeys', 'missingUnitPrice', 'earliestItemDelivery', 'stripMatPrefix', 'generateFromPicked', 'saveAll'])
const declarations: string[] = []
let loadHandler = ''
let addDisabled = ''
function collect(node: ts.Node) {
  if (ts.isFunctionDeclaration(node) && node.name && handlers.has(node.name.text)) declarations.push(node.getText(page))
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'load') loadHandler = node.getText(page)
  if (ts.isJsxOpeningElement(node) && node.attributes.properties.some(attr => attr.getText(page) === 'onClick={openCreate}')) {
    const attr = node.attributes.properties.find(p => ts.isJsxAttribute(p) && p.name.getText(page) === 'disabled')
    if (attr && ts.isJsxAttribute(attr) && attr.initializer && ts.isJsxExpression(attr.initializer))
      addDisabled = attr.initializer.expression?.getText(page) ?? ''
  }
  ts.forEachChild(node, collect)
}
collect(page)
const script = ts.transpileModule(declarations.join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText

it('allows creation only after loading and ignores an older list response after drafting', async () => {
  const pending: ((response: unknown) => void)[] = []
  const state = { loading: true, ready: false, rows: [] as string[] }
  const bindings = {
    loadRequest: { current: 0 }, blobVersion: { current: '' },
    setLoading: (v: boolean) => { state.loading = v }, setListReady: (v: boolean) => { state.ready = v },
    setRows: (v: string[]) => { state.rows = v }, setDirty: vi.fn(),
    api: { get: () => new Promise(resolve => pending.push(resolve)) },
  }
  const code = ts.transpileModule(loadHandler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  const load = new Function(...Object.keys(bindings), code + '\nreturn load;')(...Object.values(bindings))
  const disabled = new Function('loading', 'listReady', 'return ' + addDisabled)
  const earlier = load(), latest = load()
  expect(disabled(state.loading, state.ready)).toBe(true)
  pending[1]({ data: [], headers: {} })
  await latest
  expect(disabled(state.loading, state.ready)).toBe(false)
  state.rows.push('local draft')
  pending[0]({ data: [], headers: {} })
  await earlier
  expect(state.rows).toEqual(['local draft'])
  expect(disabled(false, false)).toBe(true)
})

it('generates and saves separate factory/customer drafts without changing a historical workshop', async () => {
  const oldOrder = { no: 'OLD/A', workshop: '兴信A车间', category: '车缝',
    items: [{ moldId: 'X', qty: 3, unitPrice: 9 }] }
  let rows: any[] = [oldOrder]
  const moldings = [{ moldId: 'X', moldName: 'X', workshop: '兴信B车间' }, { moldId: 'Y', moldName: 'Y', workshop: '华康D' }]
  const api = { get: vi.fn(async () => ({ data: { moldings } })), put: vi.fn(async () => ({ headers: {} })) }
  const render = () => {
    const bindings = {
      rows, setRows: (update: (value: any[]) => any[]) => { rows = update(rows) },
      pickerSel: [0, 1], schedRows: [{ code: 'X', customer: 'A', qty: 3 }, { code: 'X', customer: 'B', qty: 4 }],
      productionFactories, fallbackFactory: '华兴', blobVersion: { current: 'previous' }, api, dayjs,
      message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
      setDirty: vi.fn(), setPickerOpen: vi.fn(), setPickerSel: vi.fn(), setLoading: vi.fn(),
    }
    return new Function(...Object.keys(bindings), script + '\nreturn { generateFromPicked, saveAll };')(...Object.values(bindings))
  }
  await render().generateFromPicked()
  expect(rows.slice(0, 4).map(row => [row.customer, row.workshop, row.items[0].qty])).toEqual([
    ['A', '华兴', 3], ['A', '华康D', 3], ['B', '华兴', 4], ['B', '华康D', 4],
  ])
  expect(new Set(rows.map(row => row.no)).size).toBe(5)
  expect(rows[0].items[0].unitPrice).toBeUndefined()
  expect(rows[4]).toEqual(oldOrder)
  await render().saveAll()
  expect(api.put).toHaveBeenCalledWith('/molding-pos/blob', rows, { headers: { 'X-Expected-Version': 'previous' } })
})
