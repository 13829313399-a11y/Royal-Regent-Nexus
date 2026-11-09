// 华康A 面单（台账）自动填充与核对：把系统按记录算出的发票数据回填到面单右侧大陆发票区。
// 面单结构（《香港--大陆票 面单(ZURU).xlsx》，sheet 名「X月份」，注意 6 月 sheet 名带尾随空格）：
//   - 每月一个 sheet；r1 标题、r2 表头、r3+ 数据行；合计行与全 0 占位行跳过
//   - 左侧（香港发票，文员手打，一律不动）：A日期 B客名 C发票NO D金额USD F实收HK G备注
//   - 右侧（大陆发票，填充目标）：J日期(9) K发票NO(10) L金额USD(11) N实收HK O备注
//   - 文员原稿右侧全是公式（J=A、K=C、L=D*0.967、N=L*7.75）——×0.967 的捷径在特殊票上会错，
//     本模块用系统真值覆写 J/K/L（N 公式保留，引用 L 自动重算）
// 填充口径（2026-10-05 与面单 1-9 月逐行核对确认）：
//   - 只写右侧 J/K/L 三列，左侧与其他列一律不动
//   - 匹配：先按左侧 C 票号在同月内精确匹配；不中再按 |左D×0.967 − 系统total| < 0.01 模糊配对
//     （配对成功即"票号疑似笔误"，照常填充并在提示里给出两边票号与位置）
//   - J=系统发票日期（以记录为准）、K=左侧 C 票号（与香港票保持一致）、L=系统票面总额（全精度）
//   - 金额差 >0.01、日期不一致、跨月位置不符、面单有系统没有、系统有面单没有——全部进提示列表
// 注意：SheetJS 写 .xls 会丢全部公式，输出必须为 .xlsx。
import * as XLSX from 'xlsx'
import { hkaInvoiceTotal } from './huakangA.js'

const COL = { J: 9, K: 10, L: 11 }

const fmtDate = (s) => {
  if (!s) return '?'
  const d = new Date((s - 25569) * 86400000)
  return `${d.getUTCMonth() + 1}-${d.getUTCDate()}`
}

// 面单里出现过的月份（sheet 名「X月份」），供前端月份筛选
export function scanHkaLedgerMonths(lwb) {
  const months = new Set()
  for (const sn of lwb.SheetNames) {
    const m = sn.match(/(\d+)月份/)
    if (m) months.add(+m[1])
  }
  return [...months].sort((a, b) => a - b)
}

// parsed：parseHkaRecords 的返回（面单只有 ZURU，只用 ZURU 票；纯计算，不需要生成工作簿，秒出）
// lwb：面单工作簿（XLSX.read 的结果）
// months：要填充/核对的月份 Set；null/undefined = 全部
export function computeHkaLedgerFills(parsed, lwb, months = null) {
  // 系统侧 ZURU 票：invNo → [inv]；取消票号集合（面单上有但记录标了取消的，提示里说明）
  const sysByNo = new Map()
  for (const inv of parsed.invoices) {
    if (inv.customer !== 'ZURU') continue
    if (!sysByNo.has(inv.invNo)) sysByNo.set(inv.invNo, [])
    sysByNo.get(inv.invNo).push(inv)
  }
  const cancelled = new Set((parsed.warnings || []).filter((w) => w.type === 'cancelled' && w.invNo).map((w) => w.invNo))

  const fills = []        // { sheet, row(1-based), J, K, L, kType }
  const amtMismatch = []  // 金额不符（>0.01），已按系统值回填
  const dateMismatch = [] // 日期不符，已按系统（记录）日期回填
  const noMismatch = []   // 票号疑似笔误（金额模糊配对成功）
  const notInSys = []     // 面单有、系统（同月）没有
  const onlySys = []      // 系统（同月）有、面单没有
  const wrongMonth = []   // 票号对得上但月份位置不符（不填）
  const stat = {}         // sheet → { filled, exact, fuzzy }

  for (const sn of lwb.SheetNames) {
    const mm = sn.match(/(\d+)月份/)
    if (!mm) continue
    const month = +mm[1]
    if (months && !months.has(month)) continue
    const ws = lwb.Sheets[sn]
    stat[sn] = { filled: 0, exact: 0, fuzzy: 0 }
    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null })

    // 系统同月票池（精确匹配 + 模糊配对的候选）
    const sysThisMonth = new Map() // invNo → inv
    for (const [no, invs] of sysByNo) for (const inv of invs) if (inv.month === month && !sysThisMonth.has(no)) sysThisMonth.set(no, inv)
    const used = new Set() // 已被配对的系统票
    const mianNos = new Set()

    // 第一遍：收集面单行并精确匹配
    const pend = [] // 精确未中的面单行，留待模糊配对
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i]
      const joined = r.map((c) => String(c ?? '')).join('|')
      if (/合计/.test(joined)) continue
      const noRaw = r[2]
      const no = noRaw === null || noRaw === undefined ? '' : String(noRaw).trim()
      if (!no || no === '发票NO:') continue
      const leftUsd = typeof r[3] === 'number' ? r[3] : null
      if (no === '0' && !leftUsd) continue // 全 0 占位行
      const rowN = i + 1
      const leftDate = typeof r[0] === 'number' ? r[0] : null
      mianNos.add(no)
      const m = { no, noRaw, leftDate, leftUsd, sn, row: rowN, month }
      const inv = sysThisMonth.get(no)
      if (inv && !used.has(inv)) {
        used.add(inv)
        doFill(m, inv)
      } else {
        pend.push(m)
      }
    }

    // 第二遍：精确未中的——先看是不是月份位置不符，再按金额模糊配对，最后进 notInSys
    for (const m of pend) {
      const elsewhere = (sysByNo.get(m.no) || []).find((inv) => !used.has(inv))
      if (elsewhere) {
        wrongMonth.push(
          `${m.no}：面单「${sn}」第${m.row}行（${month}月，${fmtDate(m.leftDate)}）↔ 系统在 ${elsewhere.month} 月，记录「${elsewhere.sheet}」第${elsewhere.row}行（${fmtDate(elsewhere.date)}）——月份位置不符，未填，请人工确认`)
        continue
      }
      // 模糊配对：同月未用票里找 |左D×0.967 − 系统total| < 0.01
      let hit = null
      if (m.leftUsd != null) {
        const target = m.leftUsd * 0.967
        for (const inv of sysThisMonth.values()) {
          if (used.has(inv)) continue
          if (Math.abs(hkaInvoiceTotal(inv) - target) < 0.01) { hit = inv; break }
        }
      }
      if (hit) {
        used.add(hit)
        stat[sn].fuzzy++
        noMismatch.push(
          `面单「${sn}」第${m.row}行 票号 ${m.no} ↔ 记录「${hit.sheet}」第${hit.row}行 票号 ${hit.invNo}：金额对得上（${fmtAmt(m.leftUsd)}×0.967≈${fmtAmt(hkaInvoiceTotal(hit))}），票号疑似笔误，已照面单票号填充，请人工核对哪边写错`)
        doFill(m, hit)
      } else {
        notInSys.push(
          `${m.no}（面单「${sn}」第${m.row}行，${fmtDate(m.leftDate)}，金额 ${m.leftUsd ?? '?'}）——系统 ${month} 月没有这张票${cancelled.has(m.no) ? '（记录在案：该票已标记取消发票）' : ''}`)
      }
    }

    // 系统同月有、面单没有
    for (const [no, inv] of sysThisMonth) {
      if (used.has(inv) || mianNos.has(no)) continue
      onlySys.push(`${no}（记录「${inv.sheet}」第${inv.row}行，${fmtDate(inv.date)}，票面 ${fmtAmt(hkaInvoiceTotal(inv))}）——面单 ${month} 月没有这一行`)
    }

    function doFill(m, inv) {
      const sysTotal = hkaInvoiceTotal(inv)
      if (m.leftUsd != null && Math.abs(sysTotal - m.leftUsd * 0.967) > 0.01)
        amtMismatch.push(
          `${m.no}：面单「${sn}」第${m.row}行 左D×0.967=${fmtAmt(m.leftUsd * 0.967)} ↔ 系统=${fmtAmt(sysTotal)}（记录「${inv.sheet}」第${inv.row}行）——已按系统值回填，请人工核对`)
      if (m.leftDate != null && inv.date != null && m.leftDate !== inv.date)
        dateMismatch.push(
          `${m.no}：面单「${sn}」第${m.row}行 日期 ${fmtDate(m.leftDate)} ↔ 记录 ${fmtDate(inv.date)}（记录「${inv.sheet}」第${inv.row}行）——已按记录日期回填，请人工核对`)
      fills.push({ sheet: sn, row: m.row, J: inv.date ?? m.leftDate, K: m.noRaw, L: sysTotal })
      stat[sn].filled++
      stat[sn].exact++
    }
  }
  // exact 计数里不含模糊配对（fuzzy 单独计）
  for (const sn of Object.keys(stat)) stat[sn].exact -= stat[sn].fuzzy
  return { fills, stat, amtMismatch, dateMismatch, noMismatch, notInSys, onlySys, wrongMonth }
}

const fmtAmt = (x) => (x == null ? '?' : (+x).toFixed(4))

// 把 fills 写进面单工作簿（就地修改，只写 J/K/L 三列）。数字格式沿用各单元格原格式。
export function fillHkaLedgerWorkbook(lwb, fills) {
  for (const f of fills) {
    const ws = lwb.Sheets[f.sheet]
    if (!ws) continue
    const r = f.row - 1
    const put = (c, cell) => {
      const ref = XLSX.utils.encode_cell({ r, c })
      const old = ws[ref]
      ws[ref] = old && old.z ? { ...cell, z: old.z } : cell
    }
    if (f.J != null) put(COL.J, { t: 'n', v: f.J })
    if (f.K !== null && f.K !== undefined)
      put(COL.K, typeof f.K === 'number' ? { t: 'n', v: f.K } : { t: 's', v: String(f.K) })
    if (f.L != null) put(COL.L, { t: 'n', v: f.L })
  }
  return lwb
}
