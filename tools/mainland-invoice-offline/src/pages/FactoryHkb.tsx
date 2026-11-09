/* eslint-disable */
// @ts-nocheck —— UI 胶水层；解析/生成逻辑在 src/lib/huakangB.js，由 scripts/hkb-verify.mjs 验证
import { useMemo, useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import JSZip from 'jszip'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { parseHkbRecord, summarizeHkb, findHkbDuplicates, generateHkbFiles } from '@/lib/huakangB.js'
import { scanLedgerMonths, computeHkbLedgerFills, fillHkbLedgerWorkbook, HKB_LEDGER_SHEETS } from '@/lib/hkbLedger.js'
import { WarnGroupsByMonth } from '@/components/WarnGroupsByMonth'
import { loadAsset } from '@/lib/loadAsset.js'
import { mergeWorkbookBuffers, reorderWorkbookSheets } from '@/lib/mergeBooks.js'

const cardCls = 'rounded-xl border-neutral-200/90 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'

const KIND_NAMES = {
  trade_ded: '贸易（扣吊柜费）', trade_noded: '贸易', trade_fee: '其它款', trade_mold: '模款',
  intl_goods: '货款', intl_inst: '模款分期', intl_mold: '模款', intl_fee: '其他款',
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

/**
 * 华康B厂区：上传《发票原件记录》→ 预览识别 → 一键生成 6 个客人发票工作簿。
 * 生成规则：票面=原始×0.967（模款/分期除外）、汇率7.75、扣减按模板公式——详见 huakangB.js。
 */
export default function FactoryHkb() {
  const [file, setFile] = useState(null)          // { name, status, parsed, error }
  const [dragOver, setDragOver] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState('')
  const [result, setResult] = useState(null)      // { files, skipped }
  const [genError, setGenError] = useState('')
  const [merging, setMerging] = useState(false)
  const [mergeNote, setMergeNote] = useState('')
  const [mergeSel, setMergeSel] = useState(new Set())
  const [genSel, setGenSel] = useState(new Set())     // 生成筛选：勾选的客人 label
  const [monthSel, setMonthSel] = useState(new Set()) // 生成筛选：勾选的月份
  const [splitDn, setSplitDn] = useState(true)        // DN/DP 开头与数字发票拆成两个文件（默认拆，可勾选取消）
  const fileRef = useRef(null)
  // 台账自动填充（右侧 I/J/K/M）
  const ledgerRef = useRef(null)
  const ledgerGenCache = useRef(null) // { parsed, files }：台账填充的 metaOnly 生成结果按源记录缓存，重复填充秒出
  const [ledger, setLedger] = useState(null)            // { name, buffer, months, sheets }
  const [ledgerMonthSel, setLedgerMonthSel] = useState(new Set())
  const [ledgerSheetSel, setLedgerSheetSel] = useState(new Set()) // 要填充的工作表
  const [ledgerBusy, setLedgerBusy] = useState(false)
  const [ledgerOverwrite, setLedgerOverwrite] = useState(false) // 覆盖已填行重填
  const [ledgerResult, setLedgerResult] = useState(null) // { fills, stat, anomalies, unfillable, skippedFilled, buffer, fileName }
  const [ledgerError, setLedgerError] = useState('')

  const onUpload = async (fileList) => {
    const f = Array.from(fileList || [])[0]
    if (!f) return
    if (!/\.xlsx?$/i.test(f.name)) {
      setFile({ name: f.name, status: 'error', error: '请上传《发票原件记录》（.xls 或 .xlsx）' })
      return
    }
    setResult(null); setGenError(''); setMergeNote('')
    setFile({ name: f.name, status: 'parsing' })
    try {
      const buffer = await f.arrayBuffer()
      const wb = XLSX.read(buffer)
      const parsed = parseHkbRecord(wb)
      parsed.summary = summarizeHkb(parsed)
      setGenSel(new Set(parsed.summary.map((g) => g.label)))
      setMonthSel(new Set(parsed.invoices.map((i) => i.month)))
      setFile({ name: f.name, status: 'done', parsed })
    } catch (e) {
      setFile({ name: f.name, status: 'error', error: String(e.message || e) })
    }
  }

  // 筛选变化后旧结果作废
  const onFilterChange = (mutate) => { mutate(); setResult(null); setMergeNote('') }

  const generate = async () => {
    if (!file?.parsed || generating) return
    setGenerating(true); setGenError(''); setResult(null); setMergeNote('')
    try {
      setProgress('加载内置模板…')
      const [trade, intl] = await Promise.all([
        loadAsset('/hkb-tpl/华康B贸易.xlsx'),
        loadAsset('/hkb-tpl/华康B国际.xlsx'),
      ])
      setProgress('生成发票工作簿…')
      const filtered = {
        ...file.parsed,
        invoices: file.parsed.invoices.filter((inv) => genSel.has(inv.label) && monthSel.has(inv.month)),
      }
      const files = await generateHkbFiles(filtered, { trade, intl }, { splitDn })
      setResult({ files, skipped: file.parsed.skipped })
      setMergeSel(new Set(files.map((x) => x.label)))
    } catch (e) {
      console.error(e)
      setGenError(String(e && e.message ? e.message : e))
    } finally { setGenerating(false); setProgress('') }
  }

  const downloadAll = async () => {
    if (!result) return
    const zip = new JSZip()
    for (const f of result.files) zip.file(f.fileName, f.buffer)
    const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `华康B发票_${timestamp()}.zip`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  // 自选合并：勾选哪些客人的发票合并进同一张表格
  const downloadMergeSel = async () => {
    if (!result || merging || mergeSel.size === 0) return
    const picked = result.files.filter((f) => mergeSel.has(f.label))
    setMerging(true); setMergeNote('')
    try {
      const { buffer: merged, renames } = await mergeWorkbookBuffers(picked.map((f) => ({ buffer: f.buffer, tag: f.label })))
      // 合并后全局重排：DN/DP 开头一组在前、数字一组在后，组内按发票号从小到大（与单文件生成同规则）
      const buffer = await reorderWorkbookSheets(merged, (nm) => {
        const dn = /^(DN|DP)/i.test(nm) ? 0 : 1
        const m = nm.match(/\d+/)
        return [dn, m ? +m[0] : 999999, nm]
      })
      downloadBlob(buffer, `华康B发票_自选合并_${timestamp()}.xlsx`)
      if (renames.length) setMergeNote(`合并工作簿里有 ${renames.length} 张重名 sheet 已加客人后缀区分：${renames.map((r) => `${r.from}→${r.to}`).join('；')}`)
    } catch (e) {
      setGenError(`自选合并失败：${e.message || e}`)
    } finally { setMerging(false) }
  }
  const mergeSelCount = result ? result.files.filter((f) => mergeSel.has(f.label)).reduce((n, f) => n + f.sheetCount, 0) : 0

  const onLedgerUpload = async (fileList) => {
    const f = Array.from(fileList || [])[0]
    if (!f) return
    if (!/\.xlsx?$/i.test(f.name)) { setLedgerError('请上传台账工作簿（.xls 或 .xlsx）'); return }
    setLedgerError(''); setLedgerResult(null); setLedger(null)
    try {
      const buffer = await f.arrayBuffer()
      const lwb0 = XLSX.read(buffer)
      const months = scanLedgerMonths(lwb0)
      if (!months.length) throw new Error('没识别到台账月份表头（应为「2026年X月份」），请确认是华康B台账工作簿')
      const sheets = HKB_LEDGER_SHEETS.filter((sn) => lwb0.Sheets[sn])
      if (!sheets.length) throw new Error('没识别到台账工作表（应为 华登（贸易）/USC（国际）/华登（实业）），请确认是华康B台账工作簿')
      setLedger({ name: f.name, buffer, months, sheets })
      // 默认不填 9 月（当月未出完票，按惯例不填），可自行勾选
      setLedgerMonthSel(new Set(months.filter((m) => m !== 9)))
      setLedgerSheetSel(new Set(sheets))
    } catch (e) {
      setLedgerError(String(e.message || e))
    }
  }

  const fillLedger = async () => {
    if (!ledger || !file?.parsed || ledgerBusy) return
    if (ledgerMonthSel.size === 0) { setLedgerError('请至少勾选一个月份'); return }
    if (ledgerSheetSel.size === 0) { setLedgerError('请至少勾选一个工作表'); return }
    setLedgerBusy(true); setLedgerError(''); setLedgerResult(null)
    try {
      // 台账金额以生成票 TOTAL 为准，这里始终用全量源记录重新生成（不受上方生成筛选影响）
      // metaOnly 只取票面元数据（TOTAL/扣减行），跳过打包 zip；结果按源记录缓存，改月份/覆盖重跑秒出
      let files
      if (ledgerGenCache.current && ledgerGenCache.current.parsed === file.parsed) {
        files = ledgerGenCache.current.files
      } else {
        const [trade, intl] = await Promise.all([
          loadAsset('/hkb-tpl/华康B贸易.xlsx'),
          loadAsset('/hkb-tpl/华康B国际.xlsx'),
        ])
        files = await generateHkbFiles(file.parsed, { trade, intl }, { metaOnly: true })
        ledgerGenCache.current = { parsed: file.parsed, files }
      }
      // 重新读取，避免重复点击时把上次写入的格子当作「已填」而跳过
      const lwb = XLSX.read(ledger.buffer, { cellStyles: true })
      const res = computeHkbLedgerFills(files, lwb, ledgerMonthSel, { overwrite: ledgerOverwrite, sheets: ledgerSheetSel })
      fillHkbLedgerWorkbook(lwb, res.fills)
      const buffer = XLSX.write(lwb, { bookType: 'xlsx', type: 'array' })
      setLedgerResult({ ...res, buffer, fileName: ledger.name.replace(/\.xlsx?$/i, '') + '_已填充.xlsx' })
    } catch (e) {
      console.error(e)
      setLedgerError(`台账填充失败：${e && e.message ? e.message : e}`)
    } finally { setLedgerBusy(false) }
  }

  const parsed = file?.status === 'done' ? file.parsed : null
  const totalInv = parsed ? parsed.invoices.length : 0
  // 月份筛选候选（按源记录段表头的 N 月）
  const allMonths = useMemo(() => {
    if (!parsed) return []
    return [...new Set(parsed.invoices.map((i) => i.month))].sort((a, b) => (a ?? 99) - (b ?? 99))
  }, [parsed])
  // 月份筛选后的各客人统计
  const filteredSummary = useMemo(() => {
    if (!parsed) return []
    return parsed.summary.map((g) => {
      const invs = parsed.invoices.filter((i) => i.label === g.label && monthSel.has(i.month))
      const kinds = new Map()
      for (const i of invs) kinds.set(i.kind, (kinds.get(i.kind) || 0) + 1)
      return { label: g.label, count: invs.length, total: g.count, kinds: [...kinds.entries()] }
    })
  }, [parsed, monthSel])
  const genCount = filteredSummary.filter((g) => genSel.has(g.label)).reduce((n, g) => n + g.count, 0)
  const monthFiltered = parsed && monthSel.size !== allMonths.length
  // 重复票提示：跨表同号 / 内容重复（示例编号=示例编号 这类同一批货开两张的情况）——只提示勾选月份内的
  const duplicates = useMemo(
    () => (parsed ? findHkbDuplicates({ ...parsed, invoices: parsed.invoices.filter((i) => monthSel.has(i.month)) }) : []),
    [parsed, monthSel],
  )
  // 跳过项同样只显示勾选月份的，未选月份（之前已处理过的）不刷屏；
  // 无月份的跳过项归「未注明月份」折叠组，不再始终显示
  const skippedGroups = useMemo(() => {
    if (!parsed) return { visible: [], unassigned: [] }
    const asItem = (s) => ({ text: `${s.sheet}${s.invNo ? ` · 发票 ${s.invNo}` : ''}：${s.reason}` })
    return {
      visible: parsed.skipped.filter((s) => s.month != null && monthSel.has(s.month)).map(asItem),
      unassigned: parsed.skipped.filter((s) => s.month == null).map(asItem),
    }
  }, [parsed, monthSel])
  // 月份筛选后仍同时含 DN/DP 开头与数字票号的客人（提供拆文件选项）；JP 系（贸易/模款/其它款）同一号码段，聚合成「JP」一项
  const dnMixInfo = useMemo(() => {
    if (!parsed) return null
    const JP_FAMILY = new Set(['JP贸易', 'JP模款', 'JP其它款'])
    const byLabel = new Map()
    for (const i of parsed.invoices.filter((x) => monthSel.has(x.month) && genSel.has(x.label))) {
      const lbl = JP_FAMILY.has(i.label) ? 'JP' : i.label
      const pre = /^(DN|DP)/i.test(String(i.invNo))
      if (!byLabel.has(lbl)) byLabel.set(lbl, { dn: 0, num: 0 })
      byLabel.get(lbl)[pre ? 'dn' : 'num']++
    }
    const m = [...byLabel.entries()].filter(([, v]) => v.dn > 0 && v.num > 0)
    return m.length ? m : null
  }, [parsed, monthSel, genSel])

  return (
    <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
      <div className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <p className="text-xs font-medium tracking-[0.2em] text-teal-700">华康B · 大陆发票</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">华康B厂区 · 发票生成</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">
            上传《发票原件记录》（.xls），系统自动按 JP贸易 / JP其它款 / JP模款 / JAKKS / USC / INDEX 六个客人生成发票工作簿。
            票面金额按 0.967 折算（模款、分期除外），吊柜费扣减按模板公式自动计算。
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card className={cardCls}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">1. 上传发票原件记录</CardTitle>
            <CardDescription>上传后立即显示识别到的段数、发票数与各客人分布。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div
              className={`flex h-32 cursor-pointer items-center justify-center rounded-xl border border-dashed transition-colors ${dragOver ? 'border-teal-600 bg-teal-50/60' : 'border-neutral-300 bg-neutral-50/60 hover:border-teal-500/60 hover:bg-teal-50/40'}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); onUpload(e.dataTransfer.files) }}
            >
              <div className="text-center">
                <div className={`mx-auto flex h-10 w-10 items-center justify-center rounded-full border bg-white shadow-sm transition-colors ${dragOver ? 'border-teal-300 text-teal-700' : 'border-neutral-200 text-neutral-400'}`}>
                  <Upload className="h-4 w-4" />
                </div>
                <div className="mt-2.5 text-sm text-neutral-600">点击选择或拖拽《发票原件记录》到这里</div>
                <div className="mt-1 text-xs text-neutral-400">支持 .xls / .xlsx</div>
              </div>
            </div>
            <input ref={fileRef} type="file" accept=".xls,.xlsx" className="hidden" aria-label="发票原件记录上传"
              onChange={(e) => { onUpload(e.target.files); e.target.value = '' }} />
          </CardContent>
        </Card>

        {file && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <FileSpreadsheet className="h-4 w-4 text-teal-700" />
                <span className="font-mono text-sm">{file.name}</span>
                {file.status === 'done' && (
                  <Badge variant="outline" className="border-teal-200 bg-teal-50 font-normal text-teal-800">
                    {parsed.segments.length} 个段 · 识别发票 {totalInv} 张
                  </Badge>
                )}
                {file.status === 'parsing' && <span className="text-xs text-neutral-400">解析中…</span>}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {file.status === 'error' && (
                <Alert variant="destructive" className="border-red-200 bg-red-50/60"><AlertDescription>{file.error}</AlertDescription></Alert>
              )}
              {parsed && (
                <>
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
                  {dnMixInfo && (
                    <label className="flex cursor-pointer items-center gap-2 text-xs text-neutral-600">
                      <input type="checkbox" className="accent-teal-700" checked={splitDn}
                        onChange={(e) => onFilterChange(() => setSplitDn(e.target.checked))} />
                      <span>
                        DN/DP 开头与数字发票分成两个文件（{dnMixInfo.map(([l, v]) => `${l}：DN开头×${v.dn} + 数字×${v.num}`).join('；')}）；
                        不勾则 JP 按 贸易/模款/其它款 分文件
                      </span>
                    </label>
                  )}
                  <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                    <table className="w-full text-sm">
                      <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                        <tr>
                          <th className="px-3 py-2.5 text-left font-medium">
                            <input type="checkbox" className="mr-1.5 align-middle accent-teal-700"
                              checked={genSel.size === filteredSummary.length && filteredSummary.length > 0}
                              onChange={(e) => onFilterChange(() => setGenSel(e.target.checked ? new Set(filteredSummary.map((g) => g.label)) : new Set()))} />
                            生成
                          </th>
                          <th className="px-3 py-2.5 text-left font-medium">输出文件（客人）</th>
                          <th className="px-3 py-2.5 text-right font-medium">发票数{monthFiltered && '（筛选后/全部）'}</th>
                          <th className="px-3 py-2.5 text-left font-medium">票型分布</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSummary.map((g) => (
                          <tr key={g.label} className={`border-t border-neutral-100 ${genSel.has(g.label) ? '' : 'opacity-40'}`}>
                            <td className="px-3 py-1.5">
                              <input type="checkbox" className="accent-teal-700" checked={genSel.has(g.label)}
                                onChange={(e) => onFilterChange(() => {
                                  const next = new Set(genSel)
                                  e.target.checked ? next.add(g.label) : next.delete(g.label)
                                  setGenSel(next)
                                })} />
                            </td>
                            <td className="px-3 py-1.5 text-xs">华康B_{g.label}发票.xlsx</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">
                              {monthFiltered ? `${g.count} / ${g.total}` : g.count}
                            </td>
                            <td className="px-3 py-1.5 text-xs text-neutral-500">
                              {g.kinds.map(([k, c]) => `${KIND_NAMES[k] || k}×${c}`).join('、') || '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <WarnGroupsByMonth
                    visible={skippedGroups.visible}
                    unassigned={skippedGroups.unassigned}
                    monthSelEmpty={monthSel.size === 0}
                    labels={{
                      visible: (n) => `勾选月份跳过的 ${n} 项：`,
                      unassigned: (n) => `未注明月份的跳过项 ${n} 条（点击展开）`,
                    }}
                  />
                  {duplicates.length > 0 && (
                    <Alert className="border-amber-200 bg-amber-50/60">
                      <AlertDescription className="text-xs">
                        <div className="font-medium text-amber-800">发现 {duplicates.length} 组重复票（仍会照常生成，请人工核对）：</div>
                        {duplicates.map((d, i) => (
                          <div key={i} className="mt-0.5 text-amber-700">
                            【{d.type}】发票 {d.invNo}：{d.detail}
                          </div>
                        ))}
                      </AlertDescription>
                    </Alert>
                  )}
                  <div className="flex items-center gap-3">
                    <Button onClick={generate} disabled={generating || genCount === 0} className="bg-teal-700 hover:bg-teal-800">
                      {generating ? (progress || '生成中…') : `2. 生成发票工作簿（${genCount} 张）`}
                    </Button>
                    {genCount === 0 && <span className="text-xs text-amber-700">请至少勾选一个客人和一个月份</span>}
                    {generating && <span className="text-xs text-neutral-400">发票较多时需要几十秒，请稍候</span>}
                  </div>
                </>
              )}
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
                共 {result.files.reduce((n, f) => n + f.sheetCount, 0)} 张发票；可整包下载、按客人单独下载，或勾选客人合并成一张表格。
                {result.files.reduce((n, f) => n + f.sheetCount, 0) > genCount && (
                  <span className="mt-1 block text-amber-700">
                    生成按钮上的 {genCount} 张是源记录里的发票数；其中 {result.files.reduce((n, f) => n + f.sheetCount, 0) - genCount} 张因货号超过单页最大行数自动拆了续票（sheet 名带 -1/-2，紧跟基号票），所以实际 {result.files.reduce((n, f) => n + f.sheetCount, 0)} 张。
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
                          checked={mergeSel.size === result.files.length && result.files.length > 0}
                          onChange={(e) => setMergeSel(e.target.checked ? new Set(result.files.map((f) => f.label)) : new Set())} />
                        合并
                      </th>
                      <th className="px-3 py-2.5 text-left font-medium">文件</th>
                      <th className="px-3 py-2.5 text-right font-medium">发票数</th>
                      <th className="px-3 py-2.5 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.files.map((f) => (
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
                  {merging ? '合并中…' : `勾选合并下载（${mergeSel.size} 个客人 · ${mergeSelCount} 张）`}
                </Button>
              </div>
              {mergeNote && <p className="text-xs text-amber-700">{mergeNote}</p>}
            </CardContent>
          </Card>
        )}

        {parsed && (
          <Card className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">4. 台账自动填充（右侧大陆发票区）</CardTitle>
              <CardDescription>
                上传台账工作簿（如 2026HK 大陆发票(1).xls），按上方源记录的生成结果自动回填右侧 I日期 / J发票号 / K金额USD / M备注。
                只写右半部分，左侧与公式不动，已填过的行自动跳过。输出为 .xlsx——浏览器写 .xls 会丢全部公式，.xlsx 完整保留。
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
                    <span className="font-medium">填充工作表：</span>
                    {ledger.sheets.map((sn) => (
                      <label key={sn} className={`inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-1 ${ledgerSheetSel.has(sn) ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-neutral-300 bg-white text-neutral-400'}`}>
                        <input type="checkbox" className="accent-teal-700" checked={ledgerSheetSel.has(sn)}
                          onChange={(e) => {
                            const next = new Set(ledgerSheetSel)
                            e.target.checked ? next.add(sn) : next.delete(sn)
                            setLedgerSheetSel(next); setLedgerResult(null)
                          }} />
                        {sn}
                      </label>
                    ))}
                    <button className="text-teal-700 hover:underline" onClick={() => { setLedgerSheetSel(new Set(ledger.sheets)); setLedgerResult(null) }}>全选</button>
                    <button className="text-teal-700 hover:underline" onClick={() => { setLedgerSheetSel(new Set()); setLedgerResult(null) }}>清空</button>
                    <span className="text-neutral-400">可多选可单选，只填充勾选的工作表</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
                    <span className="font-medium">填充月份：</span>
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
                    <span className="text-neutral-400">默认不勾 9 月（当月票未出完），需要可自行勾上</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button onClick={fillLedger} disabled={ledgerBusy || ledgerMonthSel.size === 0 || ledgerSheetSel.size === 0} className="bg-teal-700 hover:bg-teal-800">
                      {ledgerBusy ? '填充中（需重新生成全部发票，约几十秒）…' : '填充台账右侧'}
                    </Button>
                    <label className="flex cursor-pointer items-center gap-2 text-xs text-neutral-600">
                      <input type="checkbox" className="accent-teal-700" checked={ledgerOverwrite}
                        onChange={(e) => { setLedgerOverwrite(e.target.checked); setLedgerResult(null) }} />
                      覆盖已填的行（重填/刷新右侧已有内容）
                    </label>
                  </div>
                </>
              )}
              {ledgerError && (
                <Alert variant="destructive" className="border-red-200 bg-red-50/60"><AlertDescription>{ledgerError}</AlertDescription></Alert>
              )}
              {ledgerResult && (
                <div className="space-y-3">
                  {ledgerResult.fills.length === 0 && ledgerResult.skippedFilled > 0 && (
                    <Alert className="border-amber-200 bg-amber-50/60">
                      <AlertDescription className="text-xs">
                        <div className="font-medium text-amber-800">没有需要新填充的行：{ledgerResult.skippedFilled} 行右侧已有内容，已跳过。</div>
                        <div className="mt-0.5 text-amber-700">如需重填/刷新这些行，请勾选上方「覆盖已填的行」后再点填充。</div>
                      </AlertDescription>
                    </Alert>
                  )}
                  <div className="overflow-auto rounded-lg border border-neutral-200 bg-white">
                    <table className="w-full text-sm">
                      <thead className="border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                        <tr>
                          <th className="px-3 py-2.5 text-left font-medium">台账 sheet</th>
                          <th className="px-3 py-2.5 text-right font-medium">按生成票回填</th>
                          <th className="px-3 py-2.5 text-right font-medium">按左侧回填</th>
                          <th className="px-3 py-2.5 text-right font-medium">覆盖重填</th>
                          <th className="px-3 py-2.5 text-right font-medium">无法填充</th>
                          <th className="px-3 py-2.5 text-right font-medium">已填跳过</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(ledgerResult.stat).map(([sn, s]) => (
                          <tr key={sn} className="border-t border-neutral-100">
                            <td className="px-3 py-1.5 text-xs">{sn}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.gen}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.left}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.over}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.skip}</td>
                            <td className="px-3 py-1.5 text-right text-xs tabular-nums">{ledgerResult.skippedFilled}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {ledgerResult.crossMonth.length > 0 && (
                    <Alert className="border-amber-200 bg-amber-50/60">
                      <AlertDescription className="text-xs">
                        <div className="font-medium text-amber-800">跨月行 {ledgerResult.crossMonth.length} 条（发票所属月份与所在月份块不一致，未填，请人工确认）：</div>
                        {ledgerResult.crossMonth.map((u, i) => (
                          <div key={i} className="mt-0.5 text-amber-700">{u}</div>
                        ))}
                      </AlertDescription>
                    </Alert>
                  )}
                  {ledgerResult.anomalies.length > 0 && (
                    <Alert className="border-amber-200 bg-amber-50/60">
                      <AlertDescription className="text-xs">
                        <div className="font-medium text-amber-800">金额比例异常 {ledgerResult.anomalies.length} 行（生成TOTAL与左侧金额对不上，已按左侧金额回填，请人工核对）：</div>
                        {ledgerResult.anomalies.map((a, i) => (
                          <div key={i} className="mt-0.5 text-amber-700">{a}</div>
                        ))}
                      </AlertDescription>
                    </Alert>
                  )}
                  {ledgerResult.unfillable.length > 0 && (
                    <Alert className="border-amber-200 bg-amber-50/60">
                      <AlertDescription className="text-xs">
                        <div className="font-medium text-amber-800">无法填充 {ledgerResult.unfillable.length} 行（系统无生成记录且左侧不全）：</div>
                        {ledgerResult.unfillable.map((u, i) => (
                          <div key={i} className="mt-0.5 text-amber-700">{u}</div>
                        ))}
                      </AlertDescription>
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
          龙星客人按国际簿龙星模板生成（货款×0.967 折、模款不打折；S/N=订单NO列，多值留空）；同一发票号出现两张时，第二张 sheet 名自动加 ~2 后缀。
        </p>
      </div>
    </div>
  )
}
