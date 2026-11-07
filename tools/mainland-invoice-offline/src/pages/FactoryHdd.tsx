/* eslint-disable */
// @ts-nocheck —— UI 胶水层；解析/生成逻辑在 src/lib/huadeng.js
import { useMemo, useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import JSZip from 'jszip'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { HDD_CUSTOMERS, HDD_TPLS, parseHddRecords, generateHddFiles, hddInvoiceTotal, findHddDuplicates } from '@/lib/huadeng.js'
import { generateHddLedger, HDD_LEDGER_TPL_FILE } from '@/lib/hddLedger.js'
import { WarnGroupsByMonth } from '@/components/WarnGroupsByMonth'
import { loadAsset } from '@/lib/loadAsset.js'
import { mergeHddInvoiceFiles } from '@/lib/hddPrintOrder.js'
import { HddTabColorLegend } from '@/components/HddTabColorLegend'

const cardCls = 'rounded-xl border-neutral-200/90 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'

const ALL_CUSTOMERS = Object.keys(HDD_CUSTOMERS).filter((c) => !HDD_CUSTOMERS[c].skip)
const KIND_NAMES = { goods: '货款', mold: '模款', other: '其它款' }
const currencyOf = (inv) => inv.currency || HDD_CUSTOMERS[inv.customer]?.currency || '未注明币种'
const money = (n) => Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
// 先消除二进制运算尾差（如 示例编号），按 Excel 的 15 位有效数字四舍五入。
const roundMoney = (n) => Math.sign(n) * Math.round(Number((Math.abs(n) * 100).toPrecision(15))) / 100
const kindsText = (invoices) => Object.entries(invoices.reduce((acc, inv) => {
  acc[inv.kind] = (acc[inv.kind] || 0) + 1
  return acc
}, {})).map(([kind, count]) => `${KIND_NAMES[kind] || kind}×${count}`).join('、') || '—'

function amountsByCurrency(invoices, amountOf) {
  const groups = new Map()
  for (const inv of invoices) {
    const amount = amountOf(inv)
    // 续票只在最后一页记整票金额，不能将每页当成一张原票重复累计。
    if (amount === null || amount === undefined) continue
    const currency = currencyOf(inv)
    if (!groups.has(currency)) groups.set(currency, { currency, count: 0, total: 0 })
    const item = groups.get(currency)
    item.count++
    item.total += roundMoney(amount)
  }
  return [...groups.values()].sort((a, b) => a.currency.localeCompare(b.currency))
}

const timestamp = () => {
  const d = new Date()
  const pad = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function downloadBlob(buffer, name) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

/** 月份键 "2026-01" → 显示 "2026年1月"；null → 日期缺失 */
const ymLabel = (ym) => {
  if (!ym) return '日期缺失'
  const [y, m] = ym.split('-')
  return `${y}年${+m}月`
}

/** 月份分布对象 → "2026年1月:25 …" */
function monthsText(months) {
  return Object.entries(months || {})
    .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
    .map(([m, n]) => `${m === '日期缺失' ? m : ymLabel(m)}:${n}`)
    .join(' ')
}

/**
 * 华登厂区：上传《2026年华登票记录.xlsx》→ 解析预览 → 按 13 个内置模板生成发票工作簿。
 * 每个 (客户 × 票型版式) 一个文件（不同版式的样式表不兼容，不能合进同一簿）。
 * 规则：票面单价=记录×0.967（仙霸货款另乘折率=净销售/项目金额；模款全额不打折）、
 * S/N=首行合约编号、超页拆续票——详见 huadeng.js。
 */
export default function FactoryHdd() {
  const [record, setRecord] = useState(null) // { name, wb }
  const [parsed, setParsed] = useState(null)
  const [parseError, setParseError] = useState('')
  const [genSel, setGenSel] = useState(new Set())
  const [monthSel, setMonthSel] = useState(new Set())
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState('')
  const [result, setResult] = useState(null)
  const [genError, setGenError] = useState('')
  const [ledgerBusy, setLedgerBusy] = useState(false)
  const [ledgerResult, setLedgerResult] = useState(null)
  const [ledgerError, setLedgerError] = useState('')
  const [merging, setMerging] = useState(false)
  const [mergeNote, setMergeNote] = useState('')
  const [mergeSel, setMergeSel] = useState(new Set())
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [reading, setReading] = useState(false)
  const revision = useRef(0)

  // 上传/重解析/筛选变更均让旧的异步任务失效，防止旧文件或旧筛选的结果回写。
  const invalidateResult = () => {
    revision.current++
    setResult(null); setGenError(''); setMergeNote(''); setMergeSel(new Set())
    setGenerating(false); setProgress(''); setMerging(false)
    setLedgerBusy(false); setLedgerResult(null); setLedgerError('')
  }

  const onPicked = async (fileList) => {
    const f = Array.from(fileList || [])[0]
    if (!f) return
    invalidateResult()
    const currentRevision = revision.current
    setRecord(null); setParsed(null); setParseError(''); setGenSel(new Set()); setMonthSel(new Set()); setReading(false)
    if (!/\.(et|xlsx?|xlsm)$/i.test(f.name)) { setParseError('请上传记录文件（.et / .xls / .xlsx）'); return }
    setReading(true)
    try {
      const buffer = await f.arrayBuffer()
      const wb = XLSX.read(buffer)
      if (currentRevision !== revision.current) return
      setRecord({ name: f.name, wb })
    } catch (e) {
      if (currentRevision === revision.current) setParseError(`读取失败：${e && e.message ? e.message : e}`)
    } finally { if (currentRevision === revision.current) setReading(false) }
  }

  const doParse = () => {
    if (!record || reading) return
    invalidateResult(); setParseError('')
    try {
      const p = parseHddRecords(record.wb)
      setParsed(p)
      setGenSel(new Set(ALL_CUSTOMERS.filter((c) => p.summary.customers[c]?.count > 0)))
      setMonthSel(new Set(p.invoices.map((i) => i.ym ?? null)))
    } catch (e) {
      console.error(e)
      setParseError(String(e && e.message ? e.message : e))
      setParsed(null)
    }
  }

  const onFilterChange = (mutate) => { mutate(); invalidateResult() }

  const allMonths = useMemo(() => {
    if (!parsed) return []
    return [...new Set(parsed.invoices.map((i) => i.ym ?? null))]
      .sort((a, b) => (a === null ? 1 : b === null ? -1 : a.localeCompare(b)))
  }, [parsed])

  const customerRows = useMemo(() => {
    if (!parsed) return []
    return ALL_CUSTOMERS
      .filter((c) => parsed.summary.customers[c])
      .map((c) => ({ label: c, ...parsed.summary.customers[c],
        titles: [...new Set(parsed.invoices.filter((inv) => inv.customer === c && !inv.skip).map((inv) => `${inv.family || '—'} · ${currencyOf(inv)}`))].join(' / ') || `${HDD_CUSTOMERS[c].family ?? '—'} · ${HDD_CUSTOMERS[c].currency}`,
      }))
  }, [parsed])

  const filteredCount = useMemo(() => {
    const m = {}
    if (!parsed) return m
    for (const inv of parsed.invoices) {
      if (inv.skip) continue
      if (!monthSel.has(inv.ym ?? null)) continue
      m[inv.customer] = (m[inv.customer] || 0) + 1
    }
    return m
  }, [parsed, monthSel])
  const monthFiltered = parsed && monthSel.size !== allMonths.length
  const genCount = customerRows.filter((g) => genSel.has(g.label)).reduce((n, g) => n + (filteredCount[g.label] || 0), 0)
  const selectedInvoices = useMemo(() => parsed?.invoices.filter((inv) => !inv.skip && genSel.has(inv.customer) && monthSel.has(inv.ym ?? null)) || [], [parsed, genSel, monthSel])
  const selectedAmounts = useMemo(() => amountsByCurrency(selectedInvoices, hddInvoiceTotal), [selectedInvoices])
  const duplicates = useMemo(() => parsed ? findHddDuplicates({ ...parsed, invoices: selectedInvoices }) : [], [parsed, selectedInvoices])
  const resultAmounts = useMemo(() => amountsByCurrency(result?.flatMap((file) => file.invoices) || [], (inv) => inv.ledgerTotal), [result])

  // 票号→月份映射：警告按勾选月份归属，只提示当前勾选月份的问题（切月份即时更新）；
  // 归不到月份的（无票号的 sheet 级提示等）进「未注明月份」折叠组
  const warnGroups = useMemo(() => {
    const groups = { visible: [], unassigned: [], statics: [] }
    if (!parsed) return groups
    for (const warning of parsed.warnings) {
      // 同票号可出现在不同客户/月份，必须结合源工作表及行号归属。
      const matches = parsed.invoices.filter((inv) => String(inv.invNo) === String(warning.invNo) && (!warning.sheet || inv.sheet === warning.sheet))
      const exact = matches.find((inv) => inv.row === warning.row)
      const months = new Set((exact ? [exact] : matches).map((inv) => inv.ym ?? null))
      if (!warning.invNo || months.size !== 1) groups.unassigned.push(warning)
      else if (monthSel.has([...months][0])) groups.visible.push(warning)
    }
    return groups
  }, [parsed, monthSel])

  const generate = async () => {
    if (!parsed || generating || selectedInvoices.length === 0) return
    const currentRevision = revision.current
    setGenerating(true); setGenError(''); setResult(null); setMergeNote('')
    try {
      setProgress('加载内置模板…')
      // 一个客户可能用到多个版式（货款/模款/其它款 × 抬头族），13 个模板全部加载
      const entries = await Promise.all(
        Object.keys(HDD_TPLS).map(async (t) => [t, await loadAsset(HDD_TPLS[t].file)]))
      const tplBuffers = Object.fromEntries(entries)
      if (currentRevision !== revision.current) return
      setProgress('生成发票工作簿…')
      const files = await generateHddFiles({ ...parsed, invoices: selectedInvoices }, tplBuffers)
      if (currentRevision !== revision.current) return
      setResult(files)
      setMergeSel(new Set(files.map((x) => x.label)))
    } catch (e) {
      console.error(e)
      if (currentRevision === revision.current) setGenError(String(e && e.message ? e.message : e))
    } finally { if (currentRevision === revision.current) { setGenerating(false); setProgress('') } }
  }

  const generateLedger = async () => {
    if (!parsed || ledgerBusy || selectedInvoices.length === 0) return
    const currentRevision = revision.current
    setLedgerBusy(true); setLedgerResult(null); setLedgerError('')
    try {
      const tplBuffer = await loadAsset(HDD_LEDGER_TPL_FILE)
      if (currentRevision !== revision.current) return
      const output = await generateHddLedger({ parsed: { ...parsed, invoices: selectedInvoices }, tplBuffer })
      if (currentRevision === revision.current) setLedgerResult(output)
    } catch (e) {
      if (currentRevision === revision.current) setLedgerError(`面单生成失败：${e.message || e}`)
    } finally {
      if (currentRevision === revision.current) setLedgerBusy(false)
    }
  }

  const downloadAll = async () => {
    if (!result) return
    const currentRevision = revision.current
    try {
      const zip = new JSZip()
      for (const f of result) zip.file(f.fileName, f.buffer)
      const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
      if (currentRevision !== revision.current) return
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `华登发票_${timestamp()}.zip`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { if (currentRevision === revision.current) setGenError(`整包下载失败：${e.message || e}`) }
  }

  const downloadAudit = () => {
    if (!result) return
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(resultAmounts.map((item) => ({
      币种: item.currency, 源发票数: item.count, 票面金额合计: roundMoney(item.total),
    }))), '币种汇总')
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(result.flatMap((file) => file.invoices.map((inv) => ({
      输出文件: file.fileName, 工作表: inv.sheetName, 客户: inv.customer,
      发票号: inv.invNo, 月份: inv.ym || '日期缺失', 票型: KIND_NAMES[inv.kind] || inv.kind,
      币种: currencyOf(inv), 整票金额: inv.ledgerTotal == null ? null : roundMoney(inv.ledgerTotal), 页码: (inv.pageNo || 0) + 1,
      总页数: inv.pageCnt || 1, 源工作表: inv.sheet, 源行号: inv.row,
      待核对提示: parsed.warnings.filter((w) => String(w.invNo) === String(inv.invNo) && (!w.sheet || w.sheet === inv.sheet)).map((w) => w.text).join('；'),
    })))), '发票明细')
    const warnings = [...warnGroups.visible, ...warnGroups.unassigned].map((w) => ({
      源工作表: w.sheet || '', 源行号: w.row || '', 发票号: w.invNo || '', 提示: w.text,
    }))
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(warnings.length ? warnings : [{ 提示: '当前筛选范围没有解析问题提示；请仍核对实际票面。' }]), '问题提示')
    wb.Sheets['币种汇总']['!cols'] = [12, 14, 20].map((wch) => ({ wch }))
    wb.Sheets['发票明细']['!cols'] = [48, 22, 18, 20, 14, 14, 10, 18, 8, 10, 18, 12, 100].map((wch) => ({ wch }))
    wb.Sheets['问题提示']['!cols'] = [18, 12, 20, 100].map((wch) => ({ wch }))
    for (const [sheet, column] of [['币种汇总', 'C'], ['发票明细', 'H']]) {
      for (const [address, cell] of Object.entries(wb.Sheets[sheet])) {
        if (new RegExp(`^${column}\\d+$`).test(address) && cell.t === 'n') cell.z = '#,##0.00'
      }
    }
    downloadBlob(XLSX.write(wb, { bookType: 'xlsx', type: 'array' }), `华登发票_核对明细_${timestamp()}.xlsx`)
  }

  const downloadMergeSel = async () => {
    if (!result || merging || mergeSel.size === 0) return
    const picked = result.filter((f) => mergeSel.has(f.label))
    const currentRevision = revision.current
    setMerging(true); setMergeNote('')
    try {
      const { buffer, renames } = await mergeHddInvoiceFiles(picked)
      if (currentRevision !== revision.current) return
      downloadBlob(buffer, `华登发票_自选合并_${timestamp()}.xlsx`)
      if (renames.length) setMergeNote(`合并工作簿里有 ${renames.length} 张重名 sheet 已加客户后缀区分：${renames.map((r) => `${r.from}→${r.to}`).join('；')}`)
    } catch (e) {
      if (currentRevision === revision.current) setGenError(`自选合并失败：${e.message || e}`)
    } finally { if (currentRevision === revision.current) setMerging(false) }
  }
  const mergeSelCount = result ? result.filter((f) => mergeSel.has(f.label)).reduce((n, f) => n + f.sheetCount, 0) : 0

  return (
    <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
      <div className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <p className="text-xs font-medium tracking-[0.2em] text-teal-700">华登 · 大陆发票</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">华登厂区 · 发票生成</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">
            上传《2026年华登票记录.xlsx》，系统自动按 JAKKS / 仙霸 / SPIN / Goliath / Casdon 等客户 sheet 生成发票工作簿（抬头族 × 票型各一个内置模板，同客户多版式会拆成多个文件）。
            票面单价按 0.967 折算（仙霸货款另乘记录折率=净销售/项目金额；模款按记录分期/净销售金额，不乘 0.967），明细之间空一行，超出单页容量自动拆续页。
            实业抬头与印尼票没有专用样票，按借用版式生成并逐票标记为待人工确认，请留意警告区。
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card className={cardCls}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">1. 上传记录</CardTitle>
            <CardDescription>选择或拖入《2026年华登票记录.xlsx》（.et / .xls / .xlsx 都行）。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div
                className={`flex h-32 cursor-pointer items-center justify-center rounded-xl border border-dashed transition-colors ${dragOver ? 'border-teal-600 bg-teal-50/60' : 'border-neutral-300 bg-neutral-50/60 hover:border-teal-500/60 hover:bg-teal-50/40'}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); onPicked(e.dataTransfer.files) }}
              >
                <div className="px-4 text-center">
                  <div className={`mx-auto flex h-10 w-10 items-center justify-center rounded-full border bg-white shadow-sm transition-colors ${dragOver ? 'border-teal-300 text-teal-700' : 'border-neutral-200 text-neutral-400'}`}>
                    <Upload className="h-4 w-4" />
                  </div>
                  <div className="mt-2.5 text-sm text-neutral-600">点击选择或拖拽《2026年华登票记录.xlsx》到这里</div>
                  <div className="mt-1 text-xs text-neutral-400">15 个客户 sheet 一起解析，无需拆分（TCC 是台账格式，自动跳过）</div>
                </div>
              </div>
              <input ref={fileRef} type="file" accept=".et,.xls,.xlsx,.xlsm" className="hidden" aria-label="记录文件上传"
                onChange={(e) => { onPicked(e.target.files); e.target.value = '' }} />
              {record && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-teal-700" />
                  <span className="truncate font-mono text-neutral-600">{record.name}</span>
                  <span className="shrink-0 text-teal-700">✓ 已读取</span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Button onClick={doParse} disabled={!record || reading} className="bg-teal-700 hover:bg-teal-800">解析预览</Button>
              {reading ? <span className="text-xs text-neutral-400">正在读取记录文件…</span> : !record && <span className="text-xs text-neutral-400">请先上传记录文件</span>}
            </div>
            {parseError && (
              <Alert variant="destructive" className="border-red-200 bg-red-50/60"><AlertDescription>{parseError}</AlertDescription></Alert>
            )}
          </CardContent>
        </Card>

        {parsed && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                解析预览
                <Badge variant="outline" className="border-teal-200 bg-teal-50 font-normal text-teal-800">
                  {customerRows.filter((g) => g.count > 0).length} 个客户 · 识别发票 {parsed.invoices.filter((i) => !i.skip).length} 张
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                    <tr>
                      <th className="px-3 py-2.5 text-left font-medium">客户（记录 sheet）</th>
                      <th className="px-3 py-2.5 text-left font-medium">抬头族 / 币种</th>
                      <th className="px-3 py-2.5 text-right font-medium">票数</th>
                      <th className="px-3 py-2.5 text-left font-medium">月份分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerRows.map((g) => (
                      <tr key={g.label} className="border-t border-neutral-100">
                        <td className="px-3 py-1.5 text-xs">{g.label}</td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">
                          {g.titles}
                          {HDD_CUSTOMERS[g.label].discount && ' · 货款乘折率'}
                          {HDD_CUSTOMERS[g.label].indo && ' · 印尼票'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-xs tabular-nums">{g.count}</td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">{monthsText(g.months)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <WarnGroupsByMonth
                visible={warnGroups.visible}
                unassigned={warnGroups.unassigned}
                statics={warnGroups.statics}
                monthSelEmpty={monthSel.size === 0}
                labels={{ visible: (n) => `勾选月份待核对的 ${n} 项（已跳过项与借用版式详见各条说明）：` }}
              />
              {parsed.invoices.every((inv) => inv.skip) && (
                <p className="text-sm text-amber-700">没有可生成的发票，请核对上传文件、客户工作表及上方问题提示。</p>
              )}
            </CardContent>
          </Card>
        )}

        {parsed && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">2. 生成发票</CardTitle>
              <CardDescription>勾选要生成的客户和月份；模板全部内置，无需上传。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
                <span className="font-medium">生成月份筛选：</span>
                {allMonths.map((m) => (
                  <label key={String(m)} className={`inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-1 ${monthSel.has(m) ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-neutral-300 bg-white text-neutral-400'}`}>
                    <input type="checkbox" className="accent-teal-700" checked={monthSel.has(m)}
                      onChange={(e) => onFilterChange(() => {
                        const next = new Set(monthSel)
                        e.target.checked ? next.add(m) : next.delete(m)
                        setMonthSel(next)
                      })} />
                    {ymLabel(m)}
                  </label>
                ))}
                <button className="text-teal-700 hover:underline" onClick={() => onFilterChange(() => setMonthSel(new Set(allMonths)))}>全选</button>
                <button className="text-teal-700 hover:underline" onClick={() => onFilterChange(() => setMonthSel(new Set()))}>清空</button>
                {monthFiltered && <span className="text-amber-700">已按月份筛选，只生成勾选月份的发票</span>}
              </div>
              <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                    <tr>
                      <th className="px-3 py-2.5 text-left font-medium">
                        <input type="checkbox" className="mr-1.5 align-middle accent-teal-700"
                          aria-label="全选生成客户"
                          checked={customerRows.some((g) => g.count > 0) && customerRows.filter((g) => g.count > 0).every((g) => genSel.has(g.label))}
                          onChange={(e) => onFilterChange(() => setGenSel(e.target.checked ? new Set(customerRows.filter((g) => g.count > 0).map((g) => g.label)) : new Set()))} />
                        生成
                      </th>
                      <th className="px-3 py-2.5 text-left font-medium">输出文件（客户；多版式会拆多个文件）</th>
                      <th className="px-3 py-2.5 text-right font-medium">发票数{monthFiltered && '（筛选后/全部）'}</th>
                      <th className="px-3 py-2.5 text-left font-medium">票型分布（所选月份）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerRows.map((g) => (
                      <tr key={g.label} className={`border-t border-neutral-100 ${genSel.has(g.label) ? '' : 'opacity-40'}`}>
                        <td className="px-3 py-1.5">
                          <input type="checkbox" className="accent-teal-700" checked={genSel.has(g.label)} aria-label={`生成 ${g.label}`} disabled={g.count === 0}
                            onChange={(e) => onFilterChange(() => {
                              const next = new Set(genSel)
                              e.target.checked ? next.add(g.label) : next.delete(g.label)
                              setGenSel(next)
                            })} />
                        </td>
                        <td className="px-3 py-1.5 font-mono text-xs">华登_{g.label.replace(/[\\/:*?"<>|]/g, '_')}[…]发票.xlsx</td>
                        <td className="px-3 py-1.5 text-right text-xs tabular-nums">
                          {monthFiltered ? `${filteredCount[g.label] || 0} / ${g.count}` : g.count}
                        </td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">{kindsText(parsed.invoices.filter((inv) => !inv.skip && inv.customer === g.label && monthSel.has(inv.ym ?? null)))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {selectedAmounts.length > 0 && (
                <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-neutral-600" aria-label="所选发票金额汇总">
                  <span className="font-medium">所选发票票面金额：</span>
                  {selectedAmounts.map((item) => <span key={item.currency}>{item.currency} {money(item.total)}（{item.count} 张原票）</span>)}
                </div>
              )}
              {duplicates.length > 0 && (
                <Alert className="border-amber-200 bg-amber-50/60">
                  <AlertDescription className="text-xs">
                    <div className="font-medium text-amber-800">发现 {duplicates.length} 组重复票号（保留全部记录，请人工确认）：</div>
                    {duplicates.map((item) => <div key={item.invNo} className="mt-0.5 text-amber-700">发票 {item.invNo}：{item.invoices.map((inv) => `${inv.customer} · ${ymLabel(inv.ym)} · 第 ${inv.row} 行`).join('；')}</div>)}
                  </AlertDescription>
                </Alert>
              )}
              <div className="flex items-center gap-3">
                <Button onClick={generate} disabled={generating || genCount === 0} className="bg-teal-700 hover:bg-teal-800">
                  {generating ? (progress || '生成中…') : `生成发票工作簿（${genCount} 张）`}
                </Button>
                {genCount === 0 && <span className="text-xs text-amber-700">当前筛选没有可生成发票，请调整客户和月份</span>}
                {generating && <span className="text-xs text-neutral-400">发票较多时需要几十秒，请稍候</span>}
              </div>
            </CardContent>
          </Card>
        )}

        {genError && (
          <Alert variant="destructive" className="border-red-200 bg-red-50/60"><AlertDescription>{genError}</AlertDescription></Alert>
        )}

        {result && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">3. 下载发票</CardTitle>
              <CardDescription>
                共 {genCount} 张发票，输出 {result.reduce((n, f) => n + f.sheetCount, 0)} 页；可整包下载、按文件单独下载，或勾选合并到一个工作簿。
                <span className="mt-1 block">合并后按客户分组，同一客户的货款、模款和其它款按发票号顺序排列，续页紧跟原票，方便连续打印。</span>
                {result.reduce((n, f) => n + f.sheetCount, 0) > genCount && (
                  <span className="mt-1 block text-amber-700">
                    超出单页容量的明细增加了 {result.reduce((n, f) => n + f.sheetCount, 0) - genCount} 页续页；工作表名加 -1/-2，票面发票号码保持不变，整票 TOTAL 只在末页显示。
                  </span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <HddTabColorLegend customers={result.flatMap((file) => file.invoices.map((inv) => inv.customer))} />
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-neutral-600" aria-label="生成发票金额汇总">
                <span className="font-medium">生成发票票面金额：</span>
                {resultAmounts.map((item) => <span key={item.currency}>{item.currency} {money(item.total)}（{item.count} 张原票）</span>)}
                <span className="w-full text-neutral-400">按每张原票的 TOTAL 汇总，续页只在末页计一次；借用版式、抬头及记录异常仍须人工确认。</span>
              </div>
              <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                    <tr>
                      <th className="px-3 py-2.5 text-left font-medium">
                        <input type="checkbox" className="mr-1.5 align-middle"
                          aria-label="全选合并文件"
                          checked={mergeSel.size === result.length && result.length > 0}
                          onChange={(e) => setMergeSel(e.target.checked ? new Set(result.map((f) => f.label)) : new Set())} />
                        合并
                      </th>
                      <th className="px-3 py-2.5 text-left font-medium">文件</th>
                      <th className="px-3 py-2.5 text-right font-medium">页数</th>
                      <th className="px-3 py-2.5 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.map((f) => (
                      <tr key={f.label} className="border-t border-neutral-100">
                        <td className="px-3 py-1.5">
                          <input type="checkbox" checked={mergeSel.has(f.label)} aria-label={`合并 ${f.label}`}
                            onChange={(e) => {
                              const next = new Set(mergeSel)
                              e.target.checked ? next.add(f.label) : next.delete(f.label)
                              setMergeSel(next)
                            }} />
                        </td>
                        <td className="px-3 py-1.5 font-mono text-xs">{f.fileName}</td>
                        <td className="px-3 py-1.5 text-right text-xs tabular-nums">{f.sheetCount}</td>
                        <td className="px-3 py-1.5 text-right">
                          <button className="text-xs text-teal-700 hover:underline" onClick={() => downloadBlob(f.buffer, f.fileName)}>
                            下载
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={downloadAll} variant="outline">整包下载（zip）</Button>
                <Button onClick={downloadAudit} variant="outline">下载核对明细</Button>
                <Button onClick={downloadMergeSel} disabled={merging || mergeSel.size === 0} className="bg-teal-700 hover:bg-teal-800">
                  {merging ? '合并中…' : `勾选合并下载（${mergeSel.size} 个文件 · ${mergeSelCount} 页）`}
                </Button>
              </div>
              {mergeNote && <p className="text-xs text-amber-700">{mergeNote}</p>}
            </CardContent>
          </Card>
        )}

        {parsed && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">4. 生成面单</CardTitle>
              <CardDescription>沿用提供的 HK／大陆票记录左右对照格式，按上方勾选的客户和月份生成。每页 46 条明细，每个月内同一客户连续排列，客户内按日期、票号排列，每张原票记一行，多页发票不会重复计入。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-neutral-500">面单版式已内置，无需重复上传参考表；香港金额与大陆票面金额分别保留，按抬头和月份归类。</p>
              <Button onClick={generateLedger} disabled={ledgerBusy || genCount === 0} className="bg-teal-700 hover:bg-teal-800">
                {ledgerBusy ? '正在生成面单…' : `生成面单（${genCount} 张原票）`}
              </Button>
              {ledgerError && <Alert variant="destructive"><AlertDescription>{ledgerError}</AlertDescription></Alert>}
              {ledgerResult && (
                <div className="space-y-3" aria-label="华登面单生成结果">
                  <p className="text-sm text-teal-800">已生成 {ledgerResult.invoiceCount} 张原票的面单，共 {ledgerResult.sheets.length} 个工作表。</p>
                  <p className="text-xs text-neutral-500">{ledgerResult.sheets.map((s) => s.name).join('、')}</p>
                  <Button variant="outline" onClick={() => downloadBlob(ledgerResult.buffer, `华登面单_${timestamp()}.xlsx`)}>下载华登面单</Button>
                  {ledgerResult.warnings?.length > 0 && <details className="text-xs text-amber-700"><summary className="cursor-pointer">生成提示（{ledgerResult.warnings.length} 项）</summary><div className="mt-2 max-h-44 space-y-1 overflow-auto">{ledgerResult.warnings.map((w, i) => <p key={i}>{typeof w === 'string' ? w : w.text}</p>)}</div></details>}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <p className="text-xs text-neutral-400">
          金额为 0 的占位票及取消票会跳过；实业抬头、印尼借用版式、S/N 多合约号等情况会逐票提示，生成后仍待人工确认；
          仙霸货款折率以记录「净销售/项目金额」为准（0.95/0.7 之外的折率会提示）。
        </p>
      </div>
    </div>
  )
}
