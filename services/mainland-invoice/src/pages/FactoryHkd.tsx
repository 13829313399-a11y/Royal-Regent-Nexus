/* eslint-disable */
// @ts-nocheck —— UI 胶水层；解析/生成逻辑在 src/lib/huakangD.js
import { useMemo, useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { HKD_CUSTOMERS, HKD_TPLS, parseHkdRecords, generateHkdFiles } from '@/lib/huakangD.js'
import { scanHkdLedgerMonths, computeHkdLedgerFills, fillHkdLedgerWorkbook } from '@/lib/hkdLedger.js'
import { assertOperationAllowed, downloadBuffer, downloadZip } from '@/lib/session.js'
import { loadAsset } from '@/lib/loadAsset.js'
import { mergeWorkbookBuffers } from '@/lib/mergeBooks.js'

const cardCls = 'rounded-xl border-neutral-200/90 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'

const ALL_CUSTOMERS = Object.keys(HKD_CUSTOMERS)

const timestamp = () => {
  const d = new Date()
  const pad = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

const downloadBlob = downloadBuffer

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
 * 华康D厂区：上传《原件记录数据.et》→ 解析预览 → 按 8 个内置模板生成发票工作簿（每个客户 sheet 一个文件）。
 * 规则：票面单价=记录×0.967（思信印尼 ×0.98；模款/期款全额不打折）、S/N=合约编号、超页拆续票——详见 huakangD.js。
 */
export default function FactoryHkd() {
  const [record, setRecord] = useState(null) // { name, wb }
  const [parsed, setParsed] = useState(null)
  const [parseError, setParseError] = useState('')
  const [genSel, setGenSel] = useState(new Set())
  const [monthSel, setMonthSel] = useState(new Set())
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState('')
  const [result, setResult] = useState(null)
  const [genError, setGenError] = useState('')
  const [merging, setMerging] = useState(false)
  const [mergeNote, setMergeNote] = useState('')
  const [mergeSel, setMergeSel] = useState(new Set())
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  // 台账填充与核对（右侧大陆发票区 I日期/J发票号/K金额/M备注）
  const ledgerRef = useRef(null)
  const [ledger, setLedger] = useState(null)            // { name, buffer, months }
  const [ledgerMonthSel, setLedgerMonthSel] = useState(new Set())
  const [ledgerBusy, setLedgerBusy] = useState(false)
  const [ledgerResult, setLedgerResult] = useState(null) // { fills, stat, anomalies, unfillable, crossMonth, buffer, fileName }
  const [ledgerError, setLedgerError] = useState('')

  const onPicked = async (fileList) => {
    const f = Array.from(fileList || [])[0]
    if (!f) return
    setParsed(null); setParseError(''); setResult(null); setGenError(''); setMergeNote('')
    if (!/\.(et|xlsx?|xlsm)$/i.test(f.name)) { setParseError('请上传记录文件（.et / .xls / .xlsx）'); return }
    try {
      const buffer = await f.arrayBuffer()
      const wb = XLSX.read(buffer)
      setRecord({ name: f.name, wb })
    } catch (e) {
      setParseError(`读取失败：${e && e.message ? e.message : e}`)
    }
  }

  const doParse = () => {
    setParseError(''); setResult(null); setGenError(''); setMergeNote('')
    try {
      const p = parseHkdRecords(record.wb)
      setParsed(p)
      setGenSel(new Set(ALL_CUSTOMERS.filter((c) => p.summary.customers[c]?.count > 0)))
      setMonthSel(new Set(p.invoices.map((i) => i.ym ?? null)))
    } catch (e) {
      console.error(e)
      setParseError(String(e && e.message ? e.message : e))
      setParsed(null)
    }
  }

  const onFilterChange = (mutate) => { mutate(); setResult(null); setMergeNote('') }

  const allMonths = useMemo(() => {
    if (!parsed) return []
    return [...new Set(parsed.invoices.map((i) => i.ym ?? null))]
      .sort((a, b) => (a === null ? 1 : b === null ? -1 : a.localeCompare(b)))
  }, [parsed])

  const customerRows = useMemo(() => {
    if (!parsed) return []
    return ALL_CUSTOMERS
      .filter((c) => parsed.summary.customers[c])
      .map((c) => ({ label: c, ...parsed.summary.customers[c] }))
  }, [parsed])

  const filteredCount = useMemo(() => {
    const m = {}
    if (!parsed) return m
    for (const inv of parsed.invoices) {
      if (!monthSel.has(inv.ym ?? null)) continue
      m[inv.customer] = (m[inv.customer] || 0) + 1
    }
    return m
  }, [parsed, monthSel])
  const monthFiltered = parsed && monthSel.size !== allMonths.length
  const genCount = customerRows.filter((g) => genSel.has(g.label)).reduce((n, g) => n + (filteredCount[g.label] || 0), 0)

  const generate = async () => {
    if (!parsed || generating) return
    setGenerating(true); setGenError(''); setResult(null); setMergeNote('')
    try {
      const operation = await assertOperationAllowed()
      setProgress('加载内置模板…')
      const customers = ALL_CUSTOMERS.filter((c) => genSel.has(c))
      const tplNames = [...new Set(customers.map((c) => HKD_CUSTOMERS[c].tpl))]
      const entries = await Promise.all(tplNames.map(async (t) => [t, await loadAsset(HKD_TPLS[t].file)]))
      const tplBuffers = Object.fromEntries(entries)
      setProgress('生成发票工作簿…')
      const yms = monthSel.size === allMonths.length ? [] : [...monthSel].filter(Boolean)
      const includeNull = monthSel.has(null)
      // 月份部分勾选时：若勾了"日期缺失"需带上 null —— 用 yms 长度判断走了简化：全不筛或按 yms 筛
      const files = await generateHkdFiles(parsed, tplBuffers, {
        customers,
        yms: monthSel.size === allMonths.length ? [] : (includeNull ? [...yms, null] : yms),
      })
      await assertOperationAllowed(operation)
      setResult(files)
      setMergeSel(new Set(files.map((x) => x.label)))
    } catch (e) {
      console.error(e)
      setGenError(String(e && e.message ? e.message : e))
    } finally { setGenerating(false); setProgress('') }
  }

  const downloadAll = async () => {
    if (!result) return
    try { await downloadZip(result, `华康D发票_${timestamp()}.zip`) }
    catch (e) { setGenError(String(e.message || e)) }
  }

  const downloadMergeSel = async () => {
    if (!result || merging || mergeSel.size === 0) return
    const picked = result.filter((f) => mergeSel.has(f.label))
    setMerging(true); setMergeNote('')
    try {
      await assertOperationAllowed()
      const { buffer, renames } = await mergeWorkbookBuffers(picked.map((f) => ({ buffer: f.buffer, tag: f.label })))
      downloadBlob(buffer, `华康D发票_自选合并_${timestamp()}.xlsx`)
      if (renames.length) setMergeNote(`合并工作簿里有 ${renames.length} 张重名 sheet 已加客户后缀区分：${renames.map((r) => `${r.from}→${r.to}`).join('；')}`)
    } catch (e) {
      setGenError(`自选合并失败：${e.message || e}`)
    } finally { setMerging(false) }
  }
  const mergeSelCount = result ? result.filter((f) => mergeSel.has(f.label)).reduce((n, f) => n + f.sheetCount, 0) : 0

  const onLedgerUpload = async (fileList) => {
    const f = Array.from(fileList || [])[0]
    if (!f) return
    if (!/\.xlsx?$/i.test(f.name)) { setLedgerError('请上传台账工作簿（.xls 或 .xlsx）'); return }
    setLedgerError(''); setLedgerResult(null); setLedger(null)
    try {
      const buffer = await f.arrayBuffer()
      const { months, factory, titles } = scanHkdLedgerMonths(XLSX.read(buffer))
      if (factory && factory !== 'D')
        throw new Error(`这本是华康${factory}的台账（块标题如「${titles[0] ?? ''}」），请到华康${factory}页面填充`)
      if (!months.length) throw new Error('没识别到月份块标题（应为「…X年Y月份(…大陆发票)」），请确认是华康D台账工作簿')
      setLedger({ name: f.name, buffer, months })
      setLedgerMonthSel(new Set(months))
    } catch (e) {
      setLedgerError(String(e.message || e))
    }
  }

  const fillLedger = async () => {
    if (!ledger || !parsed || ledgerBusy) return
    if (ledgerMonthSel.size === 0) { setLedgerError('请至少勾选一个月份'); return }
    setLedgerBusy(true); setLedgerError(''); setLedgerResult(null)
    try {
      const operation = await assertOperationAllowed()
      // 纯计算（解析结果 + 票面总额公式），不需要重新生成发票工作簿，秒出
      // 重新读取台账，避免重复点击时在已覆写的簿上累积
      const lwb = XLSX.read(ledger.buffer, { cellStyles: true })
      const res = computeHkdLedgerFills(parsed, lwb, ledgerMonthSel)
      fillHkdLedgerWorkbook(lwb, res.fills)
      const buffer = XLSX.write(lwb, { bookType: 'xlsx', type: 'array' })
      await assertOperationAllowed(operation)
      setLedgerResult({ ...res, buffer, fileName: ledger.name.replace(/\.xlsx?$/i, '') + '_已填充.xlsx' })
    } catch (e) {
      console.error(e)
      setLedgerError(`台账填充失败：${e && e.message ? e.message : e}`)
    } finally { setLedgerBusy(false) }
  }

  return (
    <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
      <div className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <p className="text-xs font-medium tracking-[0.2em] text-teal-700">华康D · 大陆发票</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">华康D厂区 · 发票生成</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">
            上传《原件记录数据.et》（WPS 表格，直接选即可），系统自动按 ZURU / Jazwares / 建文 / MAXX / Index / 思信 等 15 个客户记录生成发票工作簿（每客一个内置模板）。
            票面单价按 0.967 折算（思信印尼按 0.98；模款/期款全额不打折），明细超过单页行数自动拆续票。
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card className={cardCls}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">1. 上传记录</CardTitle>
            <CardDescription>选择或拖入《原件记录数据.et》（.et / .xls / .xlsx 都行）。</CardDescription>
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
                  <div className="mt-2.5 text-sm text-neutral-600">点击选择或拖拽《原件记录数据.et》到这里</div>
                  <div className="mt-1 text-xs text-neutral-400">15 个客户 sheet 一起解析，无需拆分</div>
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
              <Button onClick={doParse} disabled={!record} className="bg-teal-700 hover:bg-teal-800">解析预览</Button>
              {!record && <span className="text-xs text-neutral-400">请先上传记录文件</span>}
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
                  {customerRows.length} 个客户 · 识别发票 {parsed.invoices.length} 张
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                    <tr>
                      <th className="px-3 py-2.5 text-left font-medium">客户（记录 sheet）</th>
                      <th className="px-3 py-2.5 text-left font-medium">模板 / 币种 / 折率</th>
                      <th className="px-3 py-2.5 text-right font-medium">票数</th>
                      <th className="px-3 py-2.5 text-left font-medium">月份分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerRows.map((g) => (
                      <tr key={g.label} className="border-t border-neutral-100">
                        <td className="px-3 py-1.5 text-xs">{g.label}</td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">
                          {HKD_CUSTOMERS[g.label].tpl} · {HKD_CUSTOMERS[g.label].currency} · ×{HKD_CUSTOMERS[g.label].rate}
                        </td>
                        <td className="px-3 py-1.5 text-right text-xs tabular-nums">{g.count}</td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">{monthsText(g.months)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {parsed.warnings.length > 0 && (
                <Alert className="border-amber-200 bg-amber-50/60">
                  <AlertDescription className="text-xs">
                    <div className="font-medium text-amber-800">警告 {parsed.warnings.length} 条（照常生成，请人工核对）：</div>
                    <div className="mt-1 max-h-48 overflow-auto pr-1">
                      {parsed.warnings.map((w, i) => (
                        <div key={i} className="mt-0.5 text-amber-700">{w.text}</div>
                      ))}
                    </div>
                  </AlertDescription>
                </Alert>
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
                          checked={genSel.size === customerRows.length && customerRows.length > 0}
                          onChange={(e) => onFilterChange(() => setGenSel(e.target.checked ? new Set(customerRows.map((g) => g.label)) : new Set()))} />
                        生成
                      </th>
                      <th className="px-3 py-2.5 text-left font-medium">输出文件（客户）</th>
                      <th className="px-3 py-2.5 text-right font-medium">发票数{monthFiltered && '（筛选后/全部）'}</th>
                      <th className="px-3 py-2.5 text-left font-medium">月份分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerRows.map((g) => (
                      <tr key={g.label} className={`border-t border-neutral-100 ${genSel.has(g.label) ? '' : 'opacity-40'}`}>
                        <td className="px-3 py-1.5">
                          <input type="checkbox" className="accent-teal-700" checked={genSel.has(g.label)}
                            onChange={(e) => onFilterChange(() => {
                              const next = new Set(genSel)
                              e.target.checked ? next.add(g.label) : next.delete(g.label)
                              setGenSel(next)
                            })} />
                        </td>
                        <td className="px-3 py-1.5 font-mono text-xs">华康D_{g.label.replace(/[\\/:*?"<>|]/g, '_')}发票.xlsx</td>
                        <td className="px-3 py-1.5 text-right text-xs tabular-nums">
                          {monthFiltered ? `${filteredCount[g.label] || 0} / ${g.count}` : g.count}
                        </td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">{monthsText(g.months)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center gap-3">
                <Button onClick={generate} disabled={generating || genCount === 0} className="bg-teal-700 hover:bg-teal-800">
                  {generating ? (progress || '生成中…') : `生成发票工作簿（${genCount} 张）`}
                </Button>
                {genCount === 0 && <span className="text-xs text-amber-700">请至少勾选一个客户和一个月份</span>}
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
                共 {result.reduce((n, f) => n + f.sheetCount, 0)} 张发票；可整包下载、按客户单独下载，或勾选客户合并成一张表格。
                {result.reduce((n, f) => n + f.sheetCount, 0) > genCount && (
                  <span className="mt-1 block text-amber-700">
                    生成按钮上的 {genCount} 张是源记录里的发票数；其中 {result.reduce((n, f) => n + f.sheetCount, 0) - genCount} 张因明细超过单页行数自动拆了续票（sheet 名带 -1/-2），所以实际 {result.reduce((n, f) => n + f.sheetCount, 0)} 张。
                  </span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                    <tr>
                      <th className="px-3 py-2.5 text-left font-medium">
                        <input type="checkbox" className="mr-1.5 align-middle"
                          checked={mergeSel.size === result.length && result.length > 0}
                          onChange={(e) => setMergeSel(e.target.checked ? new Set(result.map((f) => f.label)) : new Set())} />
                        合并
                      </th>
                      <th className="px-3 py-2.5 text-left font-medium">文件</th>
                      <th className="px-3 py-2.5 text-right font-medium">发票数</th>
                      <th className="px-3 py-2.5 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.map((f) => (
                      <tr key={f.label} className="border-t border-neutral-100">
                        <td className="px-3 py-1.5">
                          <input type="checkbox" checked={mergeSel.has(f.label)}
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
                <Button onClick={downloadMergeSel} disabled={merging || mergeSel.size === 0} className="bg-teal-700 hover:bg-teal-800">
                  {merging ? '合并中…' : `勾选合并下载（${mergeSel.size} 个客户 · ${mergeSelCount} 张）`}
                </Button>
              </div>
              {mergeNote && <p className="text-xs text-amber-700">{mergeNote}</p>}
            </CardContent>
          </Card>
        )}

        {parsed && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">4. 台账填充与核对（右侧大陆发票区）</CardTitle>
              <CardDescription>
                上传华康D台账工作簿，按上方解析出的记录自动回填右侧 I日期 / J发票号 / K金额 / M备注，并把勾选月份里所有对不上的逐条提示。
                只写右侧几列，左侧香港票区一律不动；N 列对账公式按口径自动同步（打折行 =E×折率−L，模款全额行 =E−L）。输出为 .xlsx，公式完整保留。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <input ref={ledgerRef} type="file" accept=".xls,.xlsx" className="hidden" aria-label="台账工作簿上传"
                  onChange={(e) => { onLedgerUpload(e.target.files); e.target.value = '' }} />
                <Button variant="outline" onClick={() => ledgerRef.current?.click()}>
                  {ledger ? '重新选择台账' : '选择台账工作簿'}
                </Button>
                {ledger && <span className="font-mono text-xs text-neutral-600">{ledger.name}</span>}
              </div>
              {ledger && (
                <>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
                    <span className="font-medium">填充/核对月份：</span>
                    {ledger.months.map((m) => (
                      <label key={String(m)} className={`inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-1 ${ledgerMonthSel.has(m) ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-neutral-300 bg-white text-neutral-400'}`}>
                        <input type="checkbox" className="accent-teal-700" checked={ledgerMonthSel.has(m)}
                          onChange={(e) => {
                            const next = new Set(ledgerMonthSel)
                            e.target.checked ? next.add(m) : next.delete(m)
                            setLedgerMonthSel(next); setLedgerResult(null)
                          }} />
                        {m}月
                      </label>
                    ))}
                    <button className="text-teal-700 hover:underline" onClick={() => { setLedgerMonthSel(new Set(ledger.months)); setLedgerResult(null) }}>全选</button>
                    <button className="text-teal-700 hover:underline" onClick={() => { setLedgerMonthSel(new Set()); setLedgerResult(null) }}>清空</button>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button onClick={fillLedger} disabled={ledgerBusy || ledgerMonthSel.size === 0} className="bg-teal-700 hover:bg-teal-800">
                      {ledgerBusy ? '填充并核对中…' : '填充台账右侧并核对'}
                    </Button>
                  </div>
                </>
              )}
              {ledgerError && (
                <Alert variant="destructive" className="border-red-200 bg-red-50/60"><AlertDescription>{ledgerError}</AlertDescription></Alert>
              )}
              {ledgerResult && (
                <div className="space-y-3">
                  <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                    <table className="w-full text-sm">
                      <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                        <tr>
                          <th className="px-3 py-2.5 text-left font-medium">台账 sheet</th>
                          <th className="px-3 py-2.5 text-right font-medium">按系统填充</th>
                          <th className="px-3 py-2.5 text-right font-medium">按左侧全额填充</th>
                          <th className="px-3 py-2.5 text-right font-medium">未填（系统无此票）</th>
                          <th className="px-3 py-2.5 text-right font-medium">已填跳过</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(ledgerResult.stat).map(([sn, s]) => (
                          <tr key={sn} className="border-t border-neutral-100">
                            <td className="px-3 py-1.5 text-xs">{sn}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.gen}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.left}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.skip}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.over}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {ledgerResult.skippedFilled > 0 && (
                    <p className="text-xs text-neutral-400">右侧已填过的行共 {ledgerResult.skippedFilled} 行，已跳过未动。</p>
                  )}
                  {[
                    { list: ledgerResult.anomalies, title: '金额/票号不符', desc: '已按台账口径回填，请人工核对' },
                    { list: ledgerResult.crossMonth, title: '月份位置不符', desc: '发票年月与所在块不一致，未填，请人工确认' },
                    { list: ledgerResult.unfillable, title: '台账有、系统没有', desc: '系统记录里没有这些票且左侧不全，未填，请人工确认' },
                    { list: ledgerResult.onlySys, title: '系统有、台账没有', desc: '记录里有这些票但台账勾选月份块没有对应行，未填，请人工确认' },
                  ].filter((s) => s.list.length > 0).map((s) => (
                    <Alert key={s.title} className="border-amber-200 bg-amber-50/60">
                      <AlertDescription className="text-xs">
                        <div className="font-medium text-amber-800">{s.title} {s.list.length} 条（{s.desc}）：</div>
                        <div className="mt-1 max-h-48 overflow-auto pr-1">
                          {s.list.map((u, i) => (
                            <div key={i} className="mt-0.5 text-amber-700">{u}</div>
                          ))}
                        </div>
                      </AlertDescription>
                    </Alert>
                  ))}
                  {ledgerResult.anomalies.length === 0 && ledgerResult.crossMonth.length === 0 &&
                    ledgerResult.unfillable.length === 0 && ledgerResult.onlySys.length === 0 && (
                    <Alert className="border-teal-200 bg-teal-50/60">
                      <AlertDescription className="text-xs text-teal-800">勾选月份全部对得上，没有需要人工核对的地方。</AlertDescription>
                    </Alert>
                  )}
                  <div className="flex items-center gap-3">
                    <Button onClick={() => downloadBlob(ledgerResult.buffer, ledgerResult.fileName)} className="bg-teal-700 hover:bg-teal-800">
                      下载已填充台账（{ledgerResult.fills.length} 行）
                    </Button>
                    <span className="text-xs text-neutral-400">.xlsx 格式，公式完整保留</span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <p className="text-xs text-neutral-400">
          订金票、金额为 0 的票等特殊情况都在上方警告里逐条列出，照常生成但请人工核对；JAKKS 用 MAXX 版式但币种 HK$，思信印尼票品名缺省时用项目编号。
        </p>
      </div>
    </div>
  )
}
