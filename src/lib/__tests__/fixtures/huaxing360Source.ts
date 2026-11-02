import { readFileSync } from 'node:fs'
import { createXlsxWorkbook, type XlsxCellInput } from '../../customerPriceConverters/xlsxLite'
import type { CustomerPricingSettings } from '../../customerPriceConverters/pricingSettings'
import type { Huaxing360Result } from '../../customerPriceConverters/huaxingThreeSixty'
export function huaxing360TestPricing(): CustomerPricingSettings {
  const definition = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8'))['three-sixty-huaxing']
  return { factory_id: 'huaxing', customer_id: 'three-sixty-huaxing', revision: 0, snapshot_id: 'frozen-huaxing-360', materials: definition.materials, rates: Object.fromEntries(Object.entries(definition.rates).map(([key, row]) => [key, (row as { value: number }).value])), texts: Object.fromEntries(Object.entries(definition.texts).map(([key, row]) => [key, (row as { value: string }).value])), updated_at: '', updated_by_name: '' }
}
export function huaxing360TestSource(options: { plastic?: number; purchase?: number; costs?: Array<{ category: string; description: string }>; blank?: boolean; unknown?: boolean; missingCache?: boolean; p4?: boolean; multiple?: boolean } = {}) {
  const n = options.plastic ?? 1; const count = options.costs?.length ?? options.purchase ?? 1
  const rows: XlsxCellInput[][] = Array.from({ length: 120 }, () => [])
  const set = (r: number, c: number, v: XlsxCellInput) => { rows[r - 1]![c - 1] = v }
  set(7, 1, '本次真实产品报价'); ['名称', '料型', '料重(G)', '料价(G)', '机型', '1出几套', '目标数', '啤工', '料金额'].forEach((v, i) => set(8, 3 + i, v))
  for (let i = 0; i < n; i++) { const r = 9 + i; set(r, 2, i + 1); set(r, 3, `外壳${i}`); set(r, 4, 'PP'); set(r, 5, 100); set(r, 7, '7A'); set(r, 8, 2); set(r, 10, 7.8); set(r, 11, 10) }
  const total = 9 + n; set(total, 3, `总共${n}套模具`); set(total, 5, n * 100); set(total, 10, n * 7.8); set(total, 11, n * 10)
  const dh = total + 3; set(dh, 3, '项目'); set(dh, 4, '出厂价')
  set(dh + 1, 2, '料价'); set(dh + 1, 3, '料'); set(dh + 1, 4, n * 10)
  set(dh + 2, 2, '啤工'); set(dh + 2, 3, '啤工'); set(dh + 2, 4, n * 7.8)
  for (let i = 0; i < count; i++) { const r = dh + 3 + i; set(r, 2, options.costs?.[i]?.category ?? (options.unknown && i === 0 ? '陌生类别' : '五金')); set(r, 3, options.costs?.[i]?.description ?? `螺丝${i} (2PCS)`); set(r, 4, 15.6); set(r, 5, 2) }
  const optional = dh + 3 + count; set(optional, 2, '装配工'); set(optional, 3, '包装人工'); set(optional, 4, options.blank ? undefined : options.missingCache ? { formula: '1+2' } : 7.8)
  const fr = optional + 1; set(fr, 2, '运费'); set(fr, 3, '运费'); set(fr - 1, 5, '40尺柜'); set(fr - 1, 6, '20尺柜'); set(fr, 5, 7.8); set(fr, 6, 15.6)
  set(fr + 1, 4, n * 17.8 + count * 15.6 + (options.blank || options.missingCache ? 0 : 7.8))
  set(fr + 2, 3, '码数×'); set(fr + 2, 4, 1.18); set(fr + 3, 3, '找数÷'); set(fr + 3, 4, .97)
  set(fr + 6, 3, '测试费按MOQ:50K摊分成本'); set(fr + 6, 5, { formula: '10000/50000', value: .2 }); set(fr + 6, 6, { formula: '10000/100000', value: .1 })
  set(5, 14, '彩盒尺寸：'); set(5, 15, 10); set(5, 16, 8); set(5, 17, 6)
  set(6, 14, '装箱尺码：'); set(6, 15, 20); set(6, 16, 16); set(6, 17, 12)
  set(7, 14, 'CU.FT:'); set(7, 15, 2.22); set(7, 16, 2)
  set(8, 14, '箱价:'); set(8, 15, 15.6)
  const sheets = [{ name: '旧格式 明细', rows }]
  if (options.p4) sheets.push({ name: '结构化数据', rows: [] })
  if (options.multiple) sheets.push({ name: '另一个方案', rows })
  return createXlsxWorkbook(sheets).buffer as ArrayBuffer
}
export function huaxing360TestReady(r: Huaxing360Result) {
  Object.assign(r.review, { preparedBy: '测试业务', quoteDate: '2026-10-26', revision: '1', confirmed: true })
  return r
}
