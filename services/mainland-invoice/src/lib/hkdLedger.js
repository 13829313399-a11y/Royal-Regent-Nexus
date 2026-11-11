// 华康D台账自动填充：把系统生成的发票回填到台账工作簿右侧大陆发票区（I日期/J发票号/K金额/M备注）。
// 规则（沿用华康B 台账口径，2026-10-06）：
//   - 只写右半部分（I/J/K/M 列 + N 列对账公式），左侧 A–H 与其余公式一律不动；已填过的行（右侧有值）跳过
//   - 台账本按块标题「…2026年X月份(…大陆发票)」分月；检测到标题带其他厂区（华康A/B 等）直接拒绝，防止传错簿
//   - 金额口径：普通票 K=左D×折率（思信印尼 ×0.98，其余 ×0.967）；纯模款票 K=左D 全额（不打折）；
//     订金/预付票（尾款票、订金票）K=系统票面 TOTAL（折后小计−订金，同华康B 扣减票口径）；
//     左D 缺失时回退用系统票面 TOTAL
//   - N 列对账公式按金额口径同步：打折行 =E*rate-L，全额行 =E-L（思印尼 rate=0.98）
//   - 生成 TOTAL 与所填 K 实质不符（>0.01）时记入 anomalies 提醒人工核对（订金票除外）
//   - 跨月行（发票年月≠所在块年月）不填，记入 crossMonth 前端提示
//   - 系统有、台账对应月份块没有的票列入 onlySys 提示；台账有、系统没有的列入 unfillable
//   - 货号太多拆了续票的票（基号/基号-1…）：台账一行对应整张票，按基号匹配、填整票 TOTAL
//   - 同票号多候选（ZURU/富格勒重复票号）按金额最接近取舍，仍有疑义记入 anomalies
// 注意：SheetJS 写 .xls 会丢全部公式，因此输出为 .xlsx（同华康B）。
import * as XLSX from 'xlsx'
import { invoiceRows } from './invoiceRows.js'
import { HKD_CUSTOMERS, hkdInvoiceTotal } from './huakangD.js'

const r2 = (x) => Math.round(x * 100) / 100

// 右侧列位（I=8, J=9, K=10, M=12, N=13）与左侧（A=0 日期, B=1 客名, C=2 发票NO, D=3 金额USD, F=5 备注）
const COLS = { I: 8, J: 9, K: 10, M: 12, N: 13 }
const MONTH_TITLE_RE = /(\d{4})年(\d{1,2})月份/
const FACTORY_RE = /华康\s*([A-D])|華康\s*([A-D])/

/** 台账里出现过的月份（块标题「X年Y月份」），供前端月份筛选；返回 { months, factory, titles } */
export function scanHkdLedgerMonths(lwb) {
  const months = new Set()
  let factory = null
  const titles = new Set()
  for (const sn of lwb.SheetNames) {
    const ws = lwb.Sheets[sn]; if (!ws) continue
    const rows = invoiceRows(ws)
    for (const r of rows) {
      if (!r) continue
      for (const c of r) {
        const s = String(c ?? '')
        const m = s.match(MONTH_TITLE_RE)
        if (m && s.length < 80) {
          months.add(+m[2])
          titles.add(s)
          const f = s.match(FACTORY_RE)
          if (f) factory = f[1] || f[2]
        }
      }
    }
  }
  return { months: [...months].sort((a, b) => a - b), factory, titles: [...titles] }
}

/** 票号 → 候选票列表（同票号多客人/多票时按金额最接近取舍） */
function buildGenMap(parsed) {
  const genMap = new Map()
  for (const inv of parsed.invoices) {
    const key = String(inv.invNo)
    if (!genMap.has(key)) genMap.set(key, [])
    genMap.get(key).push(inv)
  }
  return genMap
}

const lineKinds = (inv) => {
  const kinds = new Set(inv.lines.map((l) => l.kind))
  return {
    allMold: inv.lines.length > 0 && [...kinds].every((k) => k === 'mold' || k === 'descOnly'),
    hasFee: kinds.has('fee'),
    hasDeposit: kinds.has('deposit') || !!inv.depMode,
  }
}

/**
 * 计算填充计划。
 * @param parsed parseHkdRecords 的结果（纯计算，无需先生成发票工作簿，秒出）
 * @param lwb 台账工作簿（XLSX.read 结果，建议 cellStyles:true 保留数字格式）
 * @param months 要填充的月份 Set（数字）；null/undefined = 全部
 * @param opts.overwrite true 时右侧已填的行也按规则重填；默认 false 跳过
 */
export function computeHkdLedgerFills(parsed, lwb, months = null, opts = {}) {
  const { overwrite = false } = opts
  const genMap = buildGenMap(parsed)
  const fills = []
  const unfillable = []
  const anomalies = []
  const crossMonth = []
  const stat = {}
  let skippedFilled = 0
  const seen = new Set()           // 勾选月份块里出现过的票号（含已填跳过/无法填充的行）
  const blocksSelected = new Set() // 勾选范围内的「年-月」块

  for (const sn of lwb.SheetNames) {
    const ws = lwb.Sheets[sn]; if (!ws) continue
    const rows = invoiceRows(ws)
    // 只处理有月份块标题的 sheet（台账），普通 sheet 跳过
    if (!rows.some((r) => r && r.some((c) => MONTH_TITLE_RE.test(String(c ?? ''))))) continue
    stat[sn] = { gen: 0, left: 0, skip: 0, over: 0 }
    let curYear = null, curMonth = null
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i]
      const titleCell = (r || []).find((c) => MONTH_TITLE_RE.test(String(c ?? '')))
      if (titleCell) {
        const tm = String(titleCell).match(MONTH_TITLE_RE)
        curYear = +tm[1]; curMonth = +tm[2]
        if (!months || months.has(curMonth)) blocksSelected.add(`${curYear}-${String(curMonth).padStart(2, '0')}`)
        continue
      }
      if (months && !months.has(curMonth)) continue
      if (String(r?.[2] ?? '').includes('本页合计')) continue // 每页小计行不填也不提醒
      const hasL = r?.[2] != null && r[2] !== '' && r[2] !== '发票NO:'
      const hasR = r?.[9] != null && r[9] !== '' && r[9] !== '发 票 NO:'
      if (!hasL) continue
      const invNo = String(r[2]).trim()
      seen.add(invNo)
      if (hasR && !overwrite) { skippedFilled++; continue }
      const rowN = i + 1
      const leftDate = typeof r[0] === 'number' ? r[0] : null
      const leftUsd = typeof r[3] === 'number' ? r[3] : null
      const leftRm = r[5] != null && r[5] !== '' ? String(r[5]) : ''
      const cands = genMap.get(invNo) || []
      const st = stat[sn]
      if (hasR) st.over++

      // 同票号多候选：按「左D 期望金额」最接近取舍
      const rateOf = (inv) => HKD_CUSTOMERS[inv.customer]?.rate ?? 0.967
      const expectOf = (inv) => {
        if (leftUsd == null) return hkdInvoiceTotal(inv)
        const { allMold } = lineKinds(inv)
        return allMold ? leftUsd : leftUsd * rateOf(inv)
      }
      let g = null
      if (cands.length === 1) g = cands[0]
      else if (cands.length > 1) {
        g = [...cands].sort((a, b) => Math.abs(hkdInvoiceTotal(a) - expectOf(a)) - Math.abs(hkdInvoiceTotal(b) - expectOf(b)))[0]
        const totals = cands.map((c) => r2(hkdInvoiceTotal(c)))
        if (new Set(totals).size > 1)
          anomalies.push(`${sn} 第${rowN}行 发票${invNo}：同票号 ${cands.length} 张（${cands.map((c) => `${c.customer}¥${r2(hkdInvoiceTotal(c))}`).join('、')}），已按金额最接近取 ${g.customer}，请人工核对`)
      }

      // 跨月行：发票所属年月与所在块不一致 → 不填，仅提示
      const dateParts = (serial) => {
        const d = new Date(Math.round((serial - 25569) * 86400000))
        return [d.getUTCFullYear(), d.getUTCMonth() + 1]
      }
      const [invYear, invMonth] = g?.ym ? [+g.ym.split('-')[0], +g.ym.split('-')[1]]
        : (leftDate != null ? dateParts(leftDate) : [null, null])
      if (invMonth != null && curMonth != null && (invMonth !== curMonth || (invYear != null && curYear != null && invYear !== curYear))) {
        crossMonth.push(`${sn} 第${rowN}行 发票${invNo}：${invYear}年${invMonth}月票列在${curYear}年${curMonth}月块，未填，请人工确认`)
        continue
      }

      if (g) {
        const rate = rateOf(g)
        const total = hkdInvoiceTotal(g)
        const { allMold, hasFee, hasDeposit } = lineKinds(g)
        let k, nF
        if (hasDeposit) {
          // 订金/尾款票：K=票面 TOTAL（同华康B 扣减票口径），不做比例检查
          k = r2(total)
          nF = 'disc'
        } else if (allMold) {
          k = leftUsd != null ? leftUsd : r2(total)
          nF = 'full'
          if (leftUsd != null && Math.abs(total - leftUsd) > 0.01)
            anomalies.push(`${sn} 第${rowN}行 发票${invNo}：生成TOTAL=${r2(total)}、左D=${leftUsd}（模款不打折）→ 用左D，请人工核对`)
        } else if (leftUsd != null) {
          k = r2(leftUsd * rate)
          nF = 'disc'
          if (Math.abs(total - k) > 0.01)
            anomalies.push(`${sn} 第${rowN}行 发票${invNo}：生成TOTAL=${r2(total)}、左D×${rate}=${k} → 用左D×${rate}，请人工核对`)
        } else {
          k = r2(total)
          nF = allMold ? 'full' : 'disc'
        }
        const date = leftDate != null ? leftDate : g.date
        const rm = leftRm || (allMold ? '模款' : (!invHasGoods(g) && hasFee ? '其他款' : ''))
        fills.push({ sheet: sn, row: rowN, I: date, J: invNo, K: k, M: rm, nF, rate })
        st.gen++
      } else if (leftDate != null && leftUsd != null) {
        fills.push({ sheet: sn, row: rowN, I: leftDate, J: invNo, K: leftUsd, M: leftRm, nF: 'full', rate: 1 })
        st.left++
      } else {
        unfillable.push(`${sn} 第${rowN}行 ${curMonth}月 发票${invNo}：系统记录里没有此票，左侧也不全（日期=${r[0]}、金额=${r[3]}），未填`)
        st.skip++
      }
    }
  }
  // 系统有、台账勾选月份块里没有的票（续票按基号整张计，见 genMap 口径）
  const onlySys = []
  for (const inv of parsed.invoices) {
    if (!inv.ym || !blocksSelected.has(inv.ym)) continue
    if (seen.has(String(inv.invNo))) continue
    onlySys.push(`${inv.customer} ${inv.invNo}（${inv.ym}，票面总额 ${r2(hkdInvoiceTotal(inv))}）`)
  }
  return { fills, stat, anomalies, unfillable, crossMonth, onlySys, skippedFilled }
}

const invHasGoods = (inv) => inv.lines.some((l) => l.kind === 'goods' || l.kind === 'adj')

/** 把 fills 写进台账工作簿（就地修改）。数字格式从各 sheet 第 3 行复制（同华康B）。 */
export function fillHkdLedgerWorkbook(lwb, fills) {
  const fmtBySheet = new Map()
  for (const f of fills) {
    if (fmtBySheet.has(f.sheet)) continue
    const ws = lwb.Sheets[f.sheet]; if (!ws) continue
    const get = (c) => ws[XLSX.utils.encode_cell({ r: 2, c })]?.z
    fmtBySheet.set(f.sheet, { I: get(COLS.I), J: get(COLS.J) || '@', K: get(COLS.K) || '#,##0.00', M: get(COLS.M) })
  }
  const nFmt = (ws, r) => {
    for (let up = r - 1; up >= Math.max(0, r - 60); up--) {
      const c = ws[XLSX.utils.encode_cell({ r: up, c: COLS.N })]
      if (c && c.z) return c.z
    }
    return '#,##0.0'
  }
  for (const f of fills) {
    const ws = lwb.Sheets[f.sheet]; if (!ws) continue
    const fmt = fmtBySheet.get(f.sheet) || {}
    const put = (col, cell) => { ws[XLSX.utils.encode_cell({ r: f.row - 1, c: COLS[col] })] = cell }
    if (f.I != null) put('I', { t: 'n', v: f.I, z: fmt.I })
    put('J', { t: 's', v: String(f.J), z: fmt.J })
    if (f.K != null) put('K', { t: 'n', v: f.K, z: fmt.K })
    if (f.M) put('M', { t: 's', v: f.M, z: fmt.M })
    const rate = f.rate ?? 0.967
    const nF = f.nF === 'full' ? `E${f.row}-L${f.row}` : `E${f.row}*${rate}-L${f.row}`
    // 同步写缓存值：E=+D*7.75、L=+K*7.75 按台账既有公式口径算（同华康B）
    const dCell = ws[XLSX.utils.encode_cell({ r: f.row - 1, c: 3 })]
    const eCell = ws[XLSX.utils.encode_cell({ r: f.row - 1, c: 4 })]
    const E = eCell && typeof eCell.v === 'number' ? eCell.v
      : (dCell && typeof dCell.v === 'number' ? dCell.v : 0) * 7.75
    const nV = (f.nF === 'full' ? E : E * rate) - (f.K ?? 0) * 7.75
    const nRef = XLSX.utils.encode_cell({ r: f.row - 1, c: COLS.N })
    const old = ws[nRef]
    ws[nRef] = old ? { ...old, t: 'n', v: nV, f: nF } : { t: 'n', v: nV, f: nF, z: nFmt(ws, f.row - 1) }
  }
  return lwb
}
