// 华康B台账自动填充：把系统生成的发票回填到台账工作簿右侧（I日期/J发票号/K金额USD/M备注）。
// 金额规则（2026-09-23 与台账 1-7 月手工填写逐行核对确认）：
//   - 只写右半部分（I/J/K/M 列 + N 列对账公式），左侧 A–H 与其余公式一律不动；已填过的行（右侧有值）跳过
//   - N 列对账公式按金额口径同步：K=D×0.967 → =E*0.967-L；K=D 全额（模款/实业）→ =E-L
//   - 贸易/USC 普通票（货款/其它款/散件/扣减票/订金票）：K = 左D × 0.967（折后小计，
//     扣减票也填小计不填扣后 TOTAL——台账对账公式 =E*0.967-L 要求如此，1-7 月手工行全部如此）
//   - 模款/模款分期：K = 左D 全额（不打折，对账公式 =E-L）
//   - 实业：K = 左D 全额；左D 缺失时回退用生成票 TOTAL
//   - 生成 TOTAL 与上述规则值实质不符（>0.01）时记入 anomalies 提醒人工核对
//   - 跨月行（发票月份≠所在块月份）不填，记入 crossMonth 前端提示
// 注意：SheetJS 写 .xls 会丢全部公式（实测 12,631 个公式全丢），写 .xlsx 才保留，因此输出为 .xlsx。
import * as XLSX from 'xlsx'

const KIND_RM = { trade_mold: '模款', intl_mold: '模款', intl_inst: '模款', trade_fee: '其他款', intl_fee: '其他款' }
const MOLD_KINDS = new Set(['trade_mold', 'intl_mold', 'intl_inst'])
const r2 = (x) => Math.round(x * 100) / 100

// 台账三个 sheet 的右侧列（I=8, J=9, K=10, M=12）
export const HKB_LEDGER_SHEETS = ['华登（贸易）', 'USC（国际）', '华登（实业）']

// 从生成的工作簿里取每张票 sheet 的 TOTAL 单元格数值
function sheetTotal(ws) {
  const ref = ws['!ref']; if (!ref) return null
  const range = XLSX.utils.decode_range(ref)
  let found = null
  for (let r = range.s.r; r <= range.e.r; r++) for (let c = range.s.c; c <= range.e.c; c++) {
    const cell = ws[XLSX.utils.encode_cell({ r, c })]
    if (cell && typeof cell.v === 'string' && cell.v.trim() === 'TOTAL')
      for (const cc of [9, 8]) { const v = ws[XLSX.utils.encode_cell({ r, c: cc })]; if (v && typeof v.v === 'number') found = v.v }
  }
  return found
}

// 台账 sheet 里出现过的月份（列 A 的「2026年X月份」表头），供前端月份筛选
export function scanLedgerMonths(lwb) {
  const months = new Set()
  for (const sn of HKB_LEDGER_SHEETS) {
    const ws = lwb.Sheets[sn]; if (!ws) continue
    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null })
    for (const r of rows) {
      const m = String(r?.[0] ?? '').match(/(\d+)年(\d+)月份/)
      if (m) months.add(+m[2])
    }
  }
  return [...months].sort((a, b) => a - b)
}

// 生成票号 → { label, kind, date, total, hasDeduct } 映射（同一票号多客人时按 route 选）
// hasDeduct：票面是否含 Deduct/Deposit 扣减行——扣减票的票面 TOTAL 本来就 ≠ 源×0.967，
// 台账惯例（1-7 月手工填写核验）是 K=票面 TOTAL，不做比例检查
// 快路径：生成侧已在 inv.ledgerTotal / inv.ledgerHasDeduct 附带元数据（等价口径），
// 直接采用，避免把 3,780 张生成 sheet 逐张 XLSX.read 回来扫描（原路径约 26 秒）。
function buildGenMap(files) {
  const genMap = new Map()
  for (const f of files) {
    let gwb = null // 懒加载：只有遇到缺元数据的票才读簿（兼容外部构造的 files）
    for (const inv of f.invoices) {
      let total = inv.ledgerTotal, hasDeduct = inv.ledgerHasDeduct
      if (total === undefined || hasDeduct === undefined) {
        if (!gwb) gwb = XLSX.read(f.buffer)
        const sn = inv.sheetName || String(inv.invNo).slice(0, 31)
        const ws = gwb.Sheets[sn]
        total = ws ? sheetTotal(ws) : null
        hasDeduct = false
        if (ws && ws['!ref']) {
          const range = XLSX.utils.decode_range(ws['!ref'])
          outer: for (let r = range.s.r; r <= range.e.r; r++) for (let c = range.s.c; c <= range.e.c; c++) {
            const cell = ws[XLSX.utils.encode_cell({ r, c })]
            if (cell && typeof cell.v === 'string' && /Deduct|Deposit/i.test(cell.v)) { hasDeduct = true; break outer }
          }
        }
      }
      const key = `${inv.invNo}|${inv.label}`
      const prev = genMap.get(key)
      if (!prev || (prev.total == null && total != null))
        genMap.set(key, { label: inv.label, kind: inv.kind, date: inv.date, total, hasDeduct, srcSheet: inv.sheet })
    }
  }
  return genMap
}

function route(sheetName, cust) {
  if (sheetName === '华登（贸易）') return cust === '英特' ? ['INDEX'] : ['JP贸易', 'JP模款', 'JP其它款']
  if (sheetName === 'USC（国际）') return cust === '龙星客' ? ['龙星'] : cust === 'USC' ? ['USC'] : ['JAKKS']
  return ['USC', 'JAKKS']
}

// files：generateHkbFiles 的返回（全量，未按月份/客人筛选）
// lwb：台账工作簿（XLSX.read 的结果，建议带 cellStyles:true 以保留数字格式）
// months：要填充的月份 Set；null/undefined = 全部月份
// opts.overwrite：true 时右侧已填的行也按规则重填（覆盖刷新）；默认 false 跳过已填行
// opts.sheets：要填充的工作表名 Set；null/undefined = 全部三个 sheet
export function computeHkbLedgerFills(files, lwb, months = null, opts = {}) {
  const { overwrite = false, sheets = null } = opts
  const genMap = buildGenMap(files)
  const isYn = (e) => e.srcSheet.includes('印尼')
  const matchGen = (sheetName, cust, invNo) => {
    const cands = route(sheetName, cust).map(lb => genMap.get(`${invNo}|${lb}`)).filter(Boolean)
    if (!cands.length) return null
    if (sheetName === '华登（实业）') return cands.filter(isYn)[0] || null
    return cands.filter(x => !isYn(x))[0] || cands[0]
  }

  const fills = []        // { sheet, row(1-based), I, J, K, M }
  const unfillable = []
  const anomalies = []
  const crossMonth = []   // 发票所属月份与所在块不一致的行：不填，仅提示
  const stat = {}
  let skippedFilled = 0
  const monthOf = (serial) => new Date(Math.round((serial - 25569) * 86400000)).getUTCMonth() + 1

  for (const sn of HKB_LEDGER_SHEETS) {
    if (sheets && !sheets.has(sn)) continue
    const ws = lwb.Sheets[sn]; if (!ws) continue
    stat[sn] = { gen: 0, left: 0, skip: 0, over: 0 }
    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null })
    let curMonth = null
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i]
      const m = String(r[0] ?? '').match(/(\d+)年(\d+)月份/)
      if (m) { curMonth = +m[2]; continue }
      if (months && !months.has(curMonth)) continue
      if (String(r[2] ?? '').includes('本页合计')) continue // 每页小计行不填也不提醒
      const hasL = r[2] != null && r[2] !== '' && r[2] !== '发票NO:'
      const hasR = r[9] != null && r[9] !== '' && r[9] !== '发 票 NO:'
      if (!hasL) continue
      if (hasR && !overwrite) { skippedFilled++; continue }
      const rowN = i + 1
      const invNo = String(r[2])
      const leftDate = typeof r[0] === 'number' ? r[0] : null
      const leftUsd = typeof r[3] === 'number' ? r[3] : null
      const leftRm = r[5] != null && r[5] !== '' ? String(r[5]) : ''
      const g = matchGen(sn, String(r[1] ?? ''), invNo)
      const st = stat[sn]
      if (hasR) st.over++

      // 跨月行：发票本身所属月份与所在块不一致（如 9 月票预列在 8 月块）→ 不填，仅提示
      const invMonth = g && g.date != null ? monthOf(g.date) : (leftDate != null ? monthOf(leftDate) : null)
      if (invMonth != null && curMonth != null && invMonth !== curMonth) {
        crossMonth.push(`${sn} 第${rowN}行 发票${invNo}：${invMonth}月票列在${curMonth}月块，未填，请人工确认`)
        continue
      }

      if (g && g.total != null) {
        // 金额以左侧为准（台账对账公式只认左D）：普通票=左D×0.967，模款/分期=左D全额，实业=左D全额
        // nF：N 列对账公式变体（2,600+ 手工行惯例：K=D×0.967 的行 N=E×0.967−L；K=D 全额的行 N=E−L）
        let k, nF
        if (sn === '华登（实业）') {
          k = leftUsd != null ? leftUsd : r2(g.total)
          nF = 'full'
        } else if (leftUsd == null) {
          k = r2(g.total)
          nF = MOLD_KINDS.has(g.kind) ? 'full' : 'disc'
        } else if (MOLD_KINDS.has(g.kind)) {
          k = leftUsd
          nF = 'full'
          if (Math.abs(g.total - leftUsd) > 0.01)
            anomalies.push(`${sn} 第${rowN}行 发票${invNo}：生成TOTAL=${g.total}、左D=${leftUsd}（模款不打折）→ 用左D，请人工核对`)
        } else {
          k = r2(leftUsd * 0.967)
          nF = 'disc'
          // 扣减票票面 TOTAL=小计−扣减，与 K 不同属正常；无扣减行却对不上才提醒
          if (!g.hasDeduct && Math.abs(g.total - k) > 0.01)
            anomalies.push(`${sn} 第${rowN}行 发票${invNo}：生成TOTAL=${g.total}、左D×0.967=${k} → 用左D×0.967，请人工核对`)
        }
        const date = leftDate != null ? leftDate : g.date
        const rm = leftRm || KIND_RM[g.kind] || ''
        fills.push({ sheet: sn, row: rowN, I: date, J: invNo, K: k, M: rm, nF })
        st.gen++
      } else if (leftDate != null && leftUsd != null) {
        fills.push({ sheet: sn, row: rowN, I: leftDate, J: invNo, K: leftUsd, M: leftRm, nF: 'full' })
        st.left++
      } else {
        unfillable.push(`${sn} 第${rowN}行 ${curMonth}月 发票${invNo}：系统无生成、左侧不全（日期=${r[0]}、金额=${r[3]}）`)
        st.skip++
      }
    }
  }
  return { fills, stat, anomalies, unfillable, crossMonth, skippedFilled }
}

// 把 fills 写进台账工作簿（就地修改）。数字格式从各 sheet 第 3 行复制，与 LibreOffice 宏填充一致。
// 同时按金额口径同步 N 列对账公式：K=D×0.967 的行 N==E*0.967-L，K=D 全额的行（模款/实业）N==E-L
// ——台账原件 8/9 月块两种公式混用（文员复制），不改会一批差额≠0；1-7 月手工行 100% 符合此对应。
export function fillHkbLedgerWorkbook(lwb, fills) {
  const COLS = { I: 8, J: 9, K: 10, M: 12, N: 13 }
  const fmtBySheet = new Map()
  for (const sn of HKB_LEDGER_SHEETS) {
    const ws = lwb.Sheets[sn]; if (!ws) continue
    const get = (c) => ws[XLSX.utils.encode_cell({ r: 2, c })]?.z
    fmtBySheet.set(sn, { I: get(COLS.I), J: get(COLS.J) || '@', K: get(COLS.K) || '#,##0.00', M: get(COLS.M) })
  }
  // 行内缺 N 单元格时，向上找最近一个 N 单元格的数字格式
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
    const nRef = XLSX.utils.encode_cell({ r: f.row - 1, c: COLS.N })
    const nF = f.nF === 'full' ? `E${f.row}-L${f.row}` : `E${f.row}*0.967-L${f.row}`
    // 同步写缓存值（Excel 不重算时也能直接看到结果）：E=+D*7.75、L=+K*7.75 按台账既有公式口径算
    const dCell = ws[XLSX.utils.encode_cell({ r: f.row - 1, c: 3 })]
    const eCell = ws[XLSX.utils.encode_cell({ r: f.row - 1, c: 4 })]
    const E = eCell && typeof eCell.v === 'number' ? eCell.v
      : (dCell && typeof dCell.v === 'number' ? dCell.v : 0) * 7.75
    const nV = (f.nF === 'full' ? E : E * 0.967) - (f.K ?? 0) * 7.75
    const old = ws[nRef]
    ws[nRef] = old ? { ...old, t: 'n', v: nV, f: nF } : { t: 'n', v: nV, f: nF, z: nFmt(ws, f.row - 1) }
  }
  return lwb
}
