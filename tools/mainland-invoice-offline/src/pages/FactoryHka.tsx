/* eslint-disable */
// @ts-nocheck —— UI 胶水层；解析/生成逻辑在 src/lib/huakangA.js，由 scripts/hka-verify.mjs 验证
import { useMemo, useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import JSZip from 'jszip'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { HKA_CUSTOMERS, parseHkaRecords, generateHkaFiles } from '@/lib/huakangA.js'
import { scanHkaLedgerMonths, computeHkaLedgerFills, fillHkaLedgerWorkbook } from '@/lib/hkaLedger.js'
import { buildInvMonthMap, splitWarningsByMonth } from '@/lib/warnMonth.js'
import { WarnGroupsByMonth } from '@/components/WarnGroupsByMonth'
import { loadAsset } from '@/lib/loadAsset.js'
import { mergeWorkbookBuffers } from '@/lib/mergeBooks.js'

const cardCls = 'rounded-xl border-neutral-200/90 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'

const ALL_CUSTOMERS = Object.keys(HKA_CUSTOMERS)

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

/** 月份分布对象 → "1月:25 2月:1 …"（月份按数字排序，日期缺失排最后） */
function monthsText(months) {
  return Object.entries(months || {})
    .sort((a, b) => (parseInt(a[0]) || 99) - (parseInt(b[0]) || 99))
    .map(([m, n]) => `${m}:${n}`)
    .join(' ')
}

/** ZURU 记录 sheet 名带月份（「3月份」）：票号查不到月份时（取消票/空白票号）从 sheet 名兜底归属 */
const hkaSheetMonth = (w) => {
  const m = /(\d+)\s*月份?$/.exec(String(w.sheet ?? ''))
  return m ? +m[1] : undefined
}

/** 按文件名/内容识别是 ZURU 记录还是其他客记录（不怕用户放错框） */
function classifyHkaFile(name, wb) {
  if (/ZURU/i.test(name)) return 'zuru'
  if (/其他客/.test(name)) return 'other'
  const sns = (wb && wb.SheetNames) || []
  if (sns.some((s) => /月份$/.test(s))) return 'zuru' // ZURU 记录是"X月份"分 sheet
  if (sns.some((s) => ['JP', 'Headstart', '360', 'Maglc Time', 'Green Toys', 'Strottman建文', 'INTERMED', 'magic box'].includes(s))) return 'other'
  return null
}

/** 单个上传框：可一次选/拖两个文件，自动识别类型 */
function UploadBox({ zuru, other, badFiles, onPicked }) {
  const ref = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const SlotLine = ({ label, slot }) => slot && (
    <div className="flex items-center gap-2 text-xs">
      <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-teal-700" />
      <span className="shrink-0 font-medium text-neutral-700">{label}：</span>
      <span className="truncate font-mono text-neutral-600">{slot.name}</span>
      <span className="shrink-0 text-teal-700">✓ 已读取</span>
    </div>
  )
  return (
    <div>
      <div
        className={`flex h-32 cursor-pointer items-center justify-center rounded-xl border border-dashed transition-colors ${dragOver ? 'border-teal-600 bg-teal-50/60' : 'border-neutral-300 bg-neutral-50/60 hover:border-teal-500/60 hover:bg-teal-50/40'}`}
        onClick={() => ref.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); onPicked(e.dataTransfer.files) }}
      >
        <div className="px-4 text-center">
          <div className={`mx-auto flex h-10 w-10 items-center justify-center rounded-full border bg-white shadow-sm transition-colors ${dragOver ? 'border-teal-300 text-teal-700' : 'border-neutral-200 text-neutral-400'}`}>
            <Upload className="h-4 w-4" />
          </div>
          <div className="mt-2.5 text-sm text-neutral-600">点击选择或拖拽记录文件到这里（两个文件可一起选/一起拖）</div>
          <div className="mt-1 text-xs text-neutral-400">《…发票记录（ZURU）.xlsx》和《…发票记录---其他客.xls》，系统自动识别，不怕放错</div>
        </div>
      </div>
      <input ref={ref} type="file" multiple accept=".xls,.xlsx" className="hidden" aria-label="记录文件上传"
        onChange={(e) => { onPicked(e.target.files); e.target.value = '' }} />
      <div className="mt-2 space-y-1">
        <SlotLine label="ZURU 记录" slot={zuru} />
        <SlotLine label="其他客记录" slot={other} />
        {badFiles.map((n, i) => (
          <div key={i} className="text-xs text-red-600">无法识别「{n}」是 ZURU 记录还是其他客记录，未采用</div>
        ))}
      </div>
    </div>
  )
}

/**
 * 华康A厂区：上传 ZURU / 其他客 两个发票记录 → 解析预览 → 按 6 个内置模板生成发票工作簿。
 * 规则：票面单价=记录×0.967（模款全额不打折）、S/N=合约编号、>19 行拆续票——详见 huakangA.js。
 */
export default function FactoryHka() {
  const [zuru, setZuru] = useState(null)     // { name, wb }
  const [other, setOther] = useState(null)   // { name, wb }
  const [badFiles, setBadFiles] = useState([]) // 识别不了的文件名
  const [parsed, setParsed] = useState(null) // parseHkaRecords 结果
  const [parseError, setParseError] = useState('')
  const [genSel, setGenSel] = useState(new Set())     // 生成筛选：勾选的客户
  const [monthSel, setMonthSel] = useState(new Set()) // 生成筛选：勾选的月份（解析后按数据默认全选）
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState('')
  const [result, setResult] = useState(null) // generateHkaFiles 返回的文件数组
  const [genError, setGenError] = useState('')
  const [merging, setMerging] = useState(false)
  const [mergeNote, setMergeNote] = useState('')
  const [mergeSel, setMergeSel] = useState(new Set())
  // 面单（台账）填充与核对（右侧 J日期/K发票号/L金额USD）
  const ledgerRef = useRef(null)
  const [ledger, setLedger] = useState(null)            // { name, buffer, months }
  const [ledgerMonthSel, setLedgerMonthSel] = useState(new Set())
  const [ledgerBusy, setLedgerBusy] = useState(false)
  const [ledgerResult, setLedgerResult] = useState(null) // { fills, stat, amtMismatch, dateMismatch, noMismatch, notInSys, onlySys, wrongMonth, buffer, fileName }
  const [ledgerError, setLedgerError] = useState('')

  // 一次可传多个文件：逐个读取并按文件名/内容自动识别是 ZURU 记录还是其他客记录
  const onPicked = async (fileList) => {
    const files = Array.from(fileList || [])
    if (!files.length) return
    // 记录变化后旧的解析/生成结果作废
    setParsed(null); setParseError(''); setResult(null); setGenError(''); setMergeNote('')
    setBadFiles([])
    for (const f of files) {
      try {
        const buffer = await f.arrayBuffer()
        const wb = XLSX.read(buffer)
        const kind = classifyHkaFile(f.name, wb)
        if (kind === 'zuru') setZuru({ name: f.name, wb })
        else if (kind === 'other') setOther({ name: f.name, wb })
        else setBadFiles((prev) => [...prev, f.name])
      } catch (e) {
        setBadFiles((prev) => [...prev, `${f.name}（读取失败）`])
      }
    }
  }

  const doParse = () => {
    setParseError(''); setResult(null); setGenError(''); setMergeNote('')
    try {
      const p = parseHkaRecords(zuru?.wb || null, other?.wb || null)
      setParsed(p)
      // 默认全选有数据的客户、全选记录里出现的月份（含未标月份）
      setGenSel(new Set(ALL_CUSTOMERS.filter((c) => p.summary.customers[c]?.count > 0)))
      setMonthSel(new Set(p.invoices.map((i) => i.month)))
    } catch (e) {
      console.error(e)
      setParseError(String(e && e.message ? e.message : e))
      setParsed(null)
    }
  }

  // 筛选变化后旧的生成结果作废
  const onFilterChange = (mutate) => { mutate(); setResult(null); setMergeNote('') }

  const generate = async () => {
    if (!parsed || generating) return
    setGenerating(true); setGenError(''); setResult(null); setMergeNote('')
    try {
      setProgress('加载内置模板…')
      const customers = ALL_CUSTOMERS.filter((c) => genSel.has(c))
      const entries = await Promise.all(customers.map(async (c) => [c, await loadAsset(HKA_CUSTOMERS[c].tpl)]))
      const tplBuffers = Object.fromEntries(entries)
      setProgress('生成发票工作簿…')
      // 月份全选时不传筛选；部分勾选时只生成勾选月份（含"未标月份"项）
      const months = monthSel.size === allMonths.length ? [] : [...monthSel]
      const files = await generateHkaFiles(parsed, tplBuffers, { customers, months })
      setResult(files)
      setMergeSel(new Set(files.map((x) => x.label)))
    } catch (e) {
      console.error(e)
      setGenError(String(e && e.message ? e.message : e))
    } finally { setGenerating(false); setProgress('') }
  }

  const downloadAll = async () => {
    if (!result) return
    const zip = new JSZip()
    for (const f of result) zip.file(f.fileName, f.buffer)
    const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `华康A发票_${timestamp()}.zip`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  // 自选合并：勾选哪些客户的发票合并进同一张表格
  const downloadMergeSel = async () => {
    if (!result || merging || mergeSel.size === 0) return
    const picked = result.filter((f) => mergeSel.has(f.label))
    setMerging(true); setMergeNote('')
    try {
      const { buffer, renames } = await mergeWorkbookBuffers(picked.map((f) => ({ buffer: f.buffer, tag: f.label })))
      downloadBlob(buffer, `华康A发票_自选合并_${timestamp()}.xlsx`)
      if (renames.length) setMergeNote(`合并工作簿里有 ${renames.length} 张重名 sheet 已加客户后缀区分：${renames.map((r) => `${r.from}→${r.to}`).join('；')}`)
    } catch (e) {
      setGenError(`自选合并失败：${e.message || e}`)
    } finally { setMerging(false) }
  }
  const mergeSelCount = result ? result.filter((f) => mergeSel.has(f.label)).reduce((n, f) => n + f.sheetCount, 0) : 0

  const onLedgerUpload = async (fileList) => {
    const f = Array.from(fileList || [])[0]
    if (!f) return
    if (!/\.xlsx?$/i.test(f.name)) { setLedgerError('请上传面单工作簿（.xls 或 .xlsx）'); return }
    setLedgerError(''); setLedgerResult(null); setLedger(null)
    try {
      const buffer = await f.arrayBuffer()
      const months = scanHkaLedgerMonths(XLSX.read(buffer))
      if (!months.length) throw new Error('没识别到月份 sheet（应为「X月份」），请确认是华康A面单工作簿')
      setLedger({ name: f.name, buffer, months })
      // 默认不勾 9 月（记录 9 月尚不全），需要可自行勾上
      setLedgerMonthSel(new Set(months.filter((m) => m !== 9)))
    } catch (e) {
      setLedgerError(String(e.message || e))
    }
  }

  const fillLedger = async () => {
    if (!ledger || !parsed || ledgerBusy) return
    if (ledgerMonthSel.size === 0) { setLedgerError('请至少勾选一个月份'); return }
    setLedgerBusy(true); setLedgerError(''); setLedgerResult(null)
    try {
      // 纯计算（解析结果 + 票面总额公式），不需要重新生成发票工作簿，秒出
      // 重新读取面单，避免重复点击时在已覆写的簿上累积
      const lwb = XLSX.read(ledger.buffer, { cellStyles: true })
      const res = computeHkaLedgerFills(parsed, lwb, ledgerMonthSel)
      fillHkaLedgerWorkbook(lwb, res.fills)
      const buffer = XLSX.write(lwb, { bookType: 'xlsx', type: 'array' })
      setLedgerResult({ ...res, buffer, fileName: ledger.name.replace(/\.xlsx?$/i, '') + '_已填充.xlsx' })
    } catch (e) {
      console.error(e)
      setLedgerError(`面单填充失败：${e && e.message ? e.message : e}`)
    } finally { setLedgerBusy(false) }
  }

  // 预览行：按 HKA_CUSTOMERS 顺序列有数据的客户
  const customerRows = useMemo(() => {
    if (!parsed) return []
    return ALL_CUSTOMERS
      .filter((c) => parsed.summary.customers[c])
      .map((c) => parsed.summary.customers[c] && { label: c, ...parsed.summary.customers[c] })
      .filter(Boolean)
  }, [parsed])
  // 月份筛选候选（按记录里实际出现的月份，未标月份排最后）——与华康B 同款
  const allMonths = useMemo(() => {
    if (!parsed) return []
    return [...new Set(parsed.invoices.map((i) => i.month))].sort((a, b) => (a ?? 99) - (b ?? 99))
  }, [parsed])
  // 月份筛选后的各客户票数（筛选后/全部）
  const filteredCount = useMemo(() => {
    const m = {}
    if (!parsed) return m
    for (const inv of parsed.invoices) {
      if (!monthSel.has(inv.month)) continue
      m[inv.customer] = (m[inv.customer] || 0) + 1
    }
    return m
  }, [parsed, monthSel])
  const monthFiltered = parsed && monthSel.size !== allMonths.length
  const genCount = customerRows.filter((g) => genSel.has(g.label)).reduce((n, g) => n + (filteredCount[g.label] || 0), 0)
  const canParse = !!(zuru?.wb || other?.wb)

  // 票号→月份映射：警告按勾选月份归属，只提示当前勾选月份的问题（切月份即时更新）；
  // 取消票/空白票号等票号查不到的从 sheet 名「X月份」兜底，仍归不到的进「未注明月份」折叠组
  const invMonthMap = useMemo(() => (parsed ? buildInvMonthMap(parsed.invoices) : new Map()), [parsed])
  const warnGroups = useMemo(
    () => (parsed ? splitWarningsByMonth(parsed.warnings, invMonthMap, monthSel, undefined, hkaSheetMonth) : { visible: [], unassigned: [], statics: [] }),
    [parsed, invMonthMap, monthSel],
  )

  return (
    <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
      <div className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <p className="text-xs font-medium tracking-[0.2em] text-teal-700">华康A · 大陆发票</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">华康A厂区 · 发票生成</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">
            上传《2026年华康A发票记录（ZURU）.xlsx》和《2026年华康A发票记录---其他客.xls》，系统自动按 ZURU / Headstart / 360 / Green Toys / Maglc Time / Strottman建文 六个客人生成发票工作簿（每客一个内置模板）。
            票面单价按 0.967 折算（模款全额不打折），明细超过 19 行自动拆续票。
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card className={cardCls}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">1. 上传记录</CardTitle>
            <CardDescription>两个记录文件一起选/拖进来即可，系统自动识别哪个是 ZURU 记录、哪个是其他客记录；只传一个也能解析。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <UploadBox zuru={zuru} other={other} badFiles={badFiles} onPicked={onPicked} />
            <div className="flex items-center gap-3">
              <Button onClick={doParse} disabled={!canParse} className="bg-teal-700 hover:bg-teal-800">解析预览</Button>
              {!canParse && <span className="text-xs text-neutral-400">请先上传至少一个记录文件</span>}
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
                {parsed.summary.cancelled > 0 && (
                  <Badge variant="outline" className="border-amber-200 bg-amber-50 font-normal text-amber-800">
                    取消票 {parsed.summary.cancelled} 张不生成
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                    <tr>
                      <th className="px-3 py-2.5 text-left font-medium">客户</th>
                      <th className="px-3 py-2.5 text-right font-medium">票数</th>
                      <th className="px-3 py-2.5 text-left font-medium">月份分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerRows.map((g) => (
                      <tr key={g.label} className="border-t border-neutral-100">
                        <td className="px-3 py-1.5 text-xs">{g.label}</td>
                        <td className="px-3 py-1.5 text-right text-xs tabular-nums">{g.count}</td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">{monthsText(g.months)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {parsed.summary.emptySheets.length > 0 && (
                <Alert className="border-neutral-200 bg-neutral-50/80">
                  <AlertDescription className="text-xs text-neutral-600">
                    其他客文件里这些客户 sheet 无数据（未生成）：{parsed.summary.emptySheets.join('、')}
                  </AlertDescription>
                </Alert>
              )}
              <WarnGroupsByMonth
                visible={warnGroups.visible}
                unassigned={warnGroups.unassigned}
                statics={warnGroups.statics}
                monthSelEmpty={monthSel.size === 0}
              />
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
                    {m === null || m === undefined ? '未标月份' : `${m}月`}
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
                        <td className="px-3 py-1.5 text-xs">{HKA_CUSTOMERS[g.label].fileName}</td>
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
                    生成按钮上的 {genCount} 张是源记录里的发票数；其中 {result.reduce((n, f) => n + f.sheetCount, 0) - genCount} 张因明细超过单页 19 行自动拆了续票（sheet 名带 -1/-2），所以实际 {result.reduce((n, f) => n + f.sheetCount, 0)} 张。
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
              <CardTitle className="text-base">4. 面单填充与核对（右侧大陆发票区）</CardTitle>
              <CardDescription>
                上传《香港--大陆票 面单（ZURU).xlsx》，按上方解析出的记录自动回填右侧 J日期 / K发票号 / L金额USD，并把勾选月份里所有对不上的逐条提示。
                只写右侧三列，左侧香港票区一律不动；右侧原来的 ×0.967 公式会被系统真值替换（N 列实收 HK 公式保留，自动重算）。输出为 .xlsx，公式完整保留。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <input ref={ledgerRef} type="file" accept=".xls,.xlsx" className="hidden" aria-label="面单工作簿上传"
                  onChange={(e) => { onLedgerUpload(e.target.files); e.target.value = '' }} />
                <Button variant="outline" onClick={() => ledgerRef.current?.click()}>
                  {ledger ? '重新选择面单' : '选择面单工作簿'}
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
                    <span className="text-neutral-400">默认不勾 9 月（记录 9 月尚不全），需要可自行勾上</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button onClick={fillLedger} disabled={ledgerBusy || ledgerMonthSel.size === 0} className="bg-teal-700 hover:bg-teal-800">
                      {ledgerBusy ? '填充并核对中…' : '填充面单右侧并核对'}
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
                          <th className="px-3 py-2.5 text-left font-medium">面单 sheet</th>
                          <th className="px-3 py-2.5 text-right font-medium">已填充</th>
                          <th className="px-3 py-2.5 text-right font-medium">票号精确匹配</th>
                          <th className="px-3 py-2.5 text-right font-medium">票号笔误配对</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(ledgerResult.stat).map(([sn, s]) => (
                          <tr key={sn} className="border-t border-neutral-100">
                            <td className="px-3 py-1.5 text-xs">{sn}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.filled}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.exact}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.fuzzy}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {[
                    { list: ledgerResult.noMismatch, title: '票号疑似笔误', desc: '金额对得上但票号两边不一致，已照面单票号填充，请人工核对哪边写错' },
                    { list: ledgerResult.amtMismatch, title: '金额不符', desc: '面单左D×0.967 与系统票面总额差超过 0.01，已按系统值回填，请人工核对' },
                    { list: ledgerResult.dateMismatch, title: '日期不符', desc: '面单日期与记录日期不一致，已按记录日期回填，请人工核对' },
                    { list: ledgerResult.wrongMonth, title: '月份位置不符', desc: '票号对得上但面单与系统不在同一月份，未填，请人工确认' },
                    { list: ledgerResult.notInSys, title: '面单有、系统没有', desc: '这些行未填充，请人工确认（可能是记录缺失或票号笔误）' },
                    { list: ledgerResult.onlySys, title: '系统有、面单没有', desc: '记录里有这些票但面单对应月份没有这一行，请人工确认' },
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
                  {ledgerResult.noMismatch.length === 0 && ledgerResult.amtMismatch.length === 0 &&
                    ledgerResult.dateMismatch.length === 0 && ledgerResult.wrongMonth.length === 0 &&
                    ledgerResult.notInSys.length === 0 && ledgerResult.onlySys.length === 0 && (
                    <Alert className="border-teal-200 bg-teal-50/60">
                      <AlertDescription className="text-xs text-teal-800">勾选月份全部对得上，没有需要人工核对的地方。</AlertDescription>
                    </Alert>
                  )}
                  <div className="flex items-center gap-3">
                    <Button onClick={() => downloadBlob(ledgerResult.buffer, ledgerResult.fileName)} className="bg-teal-700 hover:bg-teal-800">
                      下载已填充面单（{ledgerResult.fills.length} 行）
                    </Button>
                    <span className="text-xs text-neutral-400">.xlsx 格式，公式完整保留</span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <p className="text-xs text-neutral-400">
          取消票不生成；错字票号照填、空白票号用占位名生成、跨月笔误已按 sheet 月份纠正、重复票号按规则取舍——全部在上方警告里逐条列出，请人工核对。
        </p>
      </div>
    </div>
  )
}
