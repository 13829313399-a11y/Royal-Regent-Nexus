/* eslint-disable */
// @ts-nocheck —— UI 胶水层；解析/生成逻辑在 src/lib/huaxing.js
import { useMemo, useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import JSZip from 'jszip'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { HXG_CUSTOMERS, HXG_VARIANTS, HXG_HEADERS, HXG_TPL_SHEETS, HXG_EXTRA_FORMAT, HXG_EXTRA_TPL, HXG_PREPRINTED_TPL, parseHxgRecords, parseHxgFeed, mergeHxgParsed, hxgEncryptedWarning, generateHxgFiles } from '@/lib/huaxing.js'
import { buildInvMonthMap, splitWarningsByMonth } from '@/lib/warnMonth.js'
import { WarnGroupsByMonth } from '@/components/WarnGroupsByMonth'
import { loadAsset } from '@/lib/loadAsset.js'
import { mergeWorkbookBuffers } from '@/lib/mergeBooks.js'

const cardCls = 'rounded-xl border-neutral-200/90 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'

// 与月份无关的静态注意（内置口径提示、文件级读取/识别问题）——折叠展示，不混在按月问题列表里
const HXG_STATIC_WARNS = new Set(['custNote', 'feedNote', 'encrypted', 'readErr', 'unknownFeed', 'feedDup'])

const ALL_CUSTOMERS = Object.keys(HXG_CUSTOMERS)

// 投喂原件的内置解密密码：2026 = 现行约定密码；VelvetSweatshop = Excel 默认加密密码
const HXG_FEED_PASSWORDS = ['2026', 'VelvetSweatshop']

/** 加密原件：注入 Buffer polyfill 后用 officecrypto-tool 依次试内置密码，成功返回解密后的字节，全失败返回 null */
async function decryptFeed(buffer) {
  if (!globalThis.Buffer) globalThis.Buffer = (await import('buffer')).Buffer
  const mod = await import('officecrypto-tool')
  const oc = mod.default || mod
  for (const password of HXG_FEED_PASSWORDS) {
    try {
      return await oc.decrypt(new Uint8Array(buffer), { password })
    } catch { /* 密码不匹配，试下一个 */ }
  }
  return null
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

/** 票型分布对象 → "香港簿Sheet2（彩星版式）:14 …" */
function variantsText(variants) {
  return Object.entries(variants || {}).map(([v, n]) => `${v}:${n}`).join(' ')
}

/**
 * 华兴厂区：上传《发票记录原件.xlsx》（11 个客户 sheet 合订本）或各客排期表原件
 * （每客一个文件，可多选混合投喂）→ 解析预览 → 按内置空模板（public/hx-tpl/，
 * 由《各客模板发票》5 本文员样票簿清理而来）生成发票工作簿，每客一个文件。
 * 规则：票面单价=记录×0.967（国际/贸易簿不打折；SHU SHU PAPA 70% 行×0.7）、
 * 彩星 Less:0.5%+4%、迪奇按记录比率反推 Less、思信 SCL/数字两种票型、超页拆续票——详见 huaxing.js。
 */
export default function FactoryHxg() {
  const [records, setRecords] = useState([]) // [{ name, wb, decrypted? } | { name, readErr, encWarn }]
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
  const [hxgPrintMode, setHxgPrintMode] = useState('auto') // 自动逐客户判断，也可明确选择套打或完整格式
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  const onPicked = async (fileList) => {
    const fs = Array.from(fileList || [])
    if (!fs.length) return
    setParsed(null); setParseError(''); setResult(null); setGenError(''); setMergeNote('')
    const okExt = (n) => /\.(et|xlsx?|xlsm)$/i.test(n)
    const bad = fs.filter((f) => !okExt(f.name))
    if (bad.length) setParseError(`以下文件不是记录/排期表文件（.et / .xls / .xlsx），已跳过：${bad.map((f) => f.name).join('、')}`)
    const list = []
    for (const f of fs) {
      if (!okExt(f.name)) continue
      const buffer = await f.arrayBuffer()
      try {
        list.push({ name: f.name, wb: XLSX.read(buffer) })
      } catch (e) {
        const encWarn = hxgEncryptedWarning(f.name, e)
        let wb = null
        if (encWarn) {
          const plain = await decryptFeed(buffer)
          if (plain) {
            try { wb = XLSX.read(plain) } catch { /* 解密成功但仍读不出，按原警告处理 */ }
          }
        }
        if (wb) list.push({ name: f.name, wb, decrypted: true })
        else list.push({ name: f.name, readErr: String((e && e.message) || e), encWarn })
      }
    }
    setRecords(list)
  }

  const doParse = () => {
    setParseError(''); setResult(null); setGenError(''); setMergeNote('')
    try {
      const parts = []
      const fileWarnings = []
      for (const rec of records) {
        if (!rec.wb) {
          fileWarnings.push(rec.encWarn || { type: 'readErr', text: `文件「${rec.name}」读取失败：${rec.readErr}` })
          continue
        }
        if (rec.wb.SheetNames.filter((sn) => HXG_CUSTOMERS[sn]).length >= 2)
          parts.push(parseHxgRecords(rec.wb)) // 多客户 sheet 合订本（发票记录原件）
        else
          parts.push(parseHxgFeed(rec.name, rec.wb)) // 单客户排期表原件投喂
      }
      if (!parts.length) { setParseError('没有可解析的文件（全部读取失败）'); setParsed(null); return }
      const merged = mergeHxgParsed(parts)
      merged.warnings.push(...fileWarnings)
      setParsed(merged)
      setGenSel(new Set(ALL_CUSTOMERS.filter((c) => merged.summary.customers[c]?.count > 0)))
      setMonthSel(new Set(merged.invoices.map((i) => i.ym ?? null)))
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

  // 票号→月份映射：警告按勾选月份归属，只提示当前勾选月份的问题（切月份即时更新）；
  // 归不到月份的进「未注明月份」折叠组，静态注意（HXG_STATIC_WARNS）单独折叠
  const invMonthMap = useMemo(() => (parsed ? buildInvMonthMap(parsed.invoices) : new Map()), [parsed])
  const warnGroups = useMemo(
    () => (parsed ? splitWarningsByMonth(parsed.warnings, invMonthMap, monthSel, HXG_STATIC_WARNS) : { visible: [], unassigned: [], statics: [] }),
    [parsed, invMonthMap, monthSel],
  )

  const generate = async () => {
    if (!parsed || generating) return
    setGenerating(true); setGenError(''); setResult(null); setMergeNote('')
    try {
      setProgress('加载内置模板…')
      const customers = ALL_CUSTOMERS.filter((c) => genSel.has(c))
      const tplNames = [...new Set([...customers.map((c) => HXG_CUSTOMERS[c].tplFile), HXG_PREPRINTED_TPL])]
      // 有其他款/模费票的客户还要加载对应格式组的其他款模费模板
      const extraFmts = new Set(
        parsed.invoices.filter((i) => i.extra && customers.includes(i.customer)).map((i) => HXG_EXTRA_FORMAT[i.customer]),
      )
      for (const f of extraFmts) tplNames.push(HXG_EXTRA_TPL[f])
      const entries = await Promise.all(tplNames.map(async (t) => [t, await loadAsset(`/hx-tpl/${t}`)]))
      const tplBuffers = Object.fromEntries(entries)
      setProgress('生成发票工作簿…')
      const yms = monthSel.size === allMonths.length ? [] : [...monthSel].filter(Boolean)
      const includeNull = monthSel.has(null)
      const files = await generateHxgFiles(parsed, tplBuffers, {
        customers,
        yms: monthSel.size === allMonths.length ? [] : (includeNull ? [...yms, null] : yms),
        noHead: hxgPrintMode === 'auto' ? 'auto' : hxgPrintMode === 'preprinted',
      })
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
    a.download = `华兴发票_${timestamp()}.zip`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const downloadMergeSel = async () => {
    if (!result || merging || mergeSel.size === 0) return
    const picked = result.filter((f) => mergeSel.has(f.label))
    setMerging(true); setMergeNote('')
    try {
      const { buffer, renames } = await mergeWorkbookBuffers(picked.map((f) => ({ buffer: f.buffer, tag: f.label })))
      downloadBlob(buffer, `华兴发票_自选合并_${timestamp()}.xlsx`)
      if (renames.length) setMergeNote(`合并工作簿里有 ${renames.length} 张重名 sheet 已加客户后缀区分：${renames.map((r) => `${r.from}→${r.to}`).join('；')}`)
    } catch (e) {
      setGenError(`自选合并失败：${e.message || e}`)
    } finally { setMerging(false) }
  }
  const mergeSelCount = result ? result.filter((f) => mergeSel.has(f.label)).reduce((n, f) => n + f.sheetCount, 0) : 0

  return (
    <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
      <div className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <p className="text-xs font-medium tracking-[0.2em] text-teal-700">华兴 · 大陆发票</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">华兴厂区 · 发票生成</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">
            上传《发票记录原件.xlsx》（11 个客户 sheet 一起解析，无需拆分）或直接投喂各客排期表原件（每客一个文件，可多选混合上传；11 个客户全部支持，文件名需含客户关键词如 Dickie / BUZZ / MAXX / 银辉 / 360 / 彩星 / 迪士尼 / SEASONS 施信 / EDU / MMI / SHUSHUPAPA），系统自动按 buzz / 迪奇 / 思信 / 彩星 / EDU / 360 / MAXX / 迪士尼 / SHU SHU PAPA / 银辉 / MMI 生成发票工作簿（每客一本内置模板）。
            所有客户票面单价按 0.967 折算（SHU SHU PAPA 70% 行再 ×0.7），彩星 Less:0.5%+4%，明细超过单页行数自动拆续票；每张票右上方红字标注记录原始总金额供核对，A4 一页打印。
            投喂排期表时同时解析各客「其它款/其他费/模具手办费」sheet：其他款×0.967（带原价镜像）、模具费全额不打折，按 有打印纸/国际/贸易 三种版式单独输出「华兴_X其他款及模费发票.xlsx」。
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card className={cardCls}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">1. 上传记录 / 排期表投喂</CardTitle>
            <CardDescription>选择或拖入《发票记录原件.xlsx》合订本，或各客排期表原件（每客一个文件，可多选混合，.et / .xls / .xlsx 都行）。</CardDescription>
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
                  <div className="mt-2.5 text-sm text-neutral-600">点击选择或拖拽文件到这里（可多选）</div>
                  <div className="mt-1 text-xs text-neutral-400">发票记录原件合订本 / 各客排期表原件可混合投喂；加密文件请另存为无密码副本后再上传</div>
                </div>
              </div>
              <input ref={fileRef} type="file" multiple accept=".et,.xls,.xlsx,.xlsm" className="hidden" aria-label="记录文件上传"
                onChange={(e) => { onPicked(e.target.files); e.target.value = '' }} />
              {records.length > 0 && (
                <div className="mt-2 space-y-1">
                  {records.map((rec, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-teal-700" />
                      <span className="truncate font-mono text-neutral-600">{rec.name}</span>
                      {rec.wb
                        ? <span className="shrink-0 text-teal-700">{rec.decrypted ? '✓ 已读取（已用内置密码解密）' : '✓ 已读取'}</span>
                        : <span className="shrink-0 text-red-600">{rec.encWarn ? '已加密（密码保护），无法读取，请另存为无密码副本后再上传' : `读取失败：${rec.readErr}`}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Button onClick={doParse} disabled={!records.length} className="bg-teal-700 hover:bg-teal-800">解析预览</Button>
              {!records.length && <span className="text-xs text-neutral-400">请先上传记录文件或排期表原件</span>}
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
                      <th className="px-3 py-2.5 text-left font-medium">模板 / 票型</th>
                      <th className="px-3 py-2.5 text-left font-medium">抬头组</th>
                      <th className="px-3 py-2.5 text-right font-medium">票数</th>
                      <th className="px-3 py-2.5 text-left font-medium">月份分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerRows.map((g) => (
                      <tr key={g.label} className="border-t border-neutral-100">
                        <td className="px-3 py-1.5 text-xs">{g.label}</td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500">
                          {HXG_CUSTOMERS[g.label].tplFile.replace(/\.xlsx$/, '')} · {variantsText(g.variants)}
                        </td>
                        <td className="px-3 py-1.5 text-xs text-neutral-500" title={HXG_HEADERS[HXG_CUSTOMERS[g.label].header]}>
                          {HXG_CUSTOMERS[g.label].header}
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
                <label htmlFor="hxg-print-mode" className="font-medium">华兴打印格式：</label>
                <select id="hxg-print-mode" aria-label="华兴打印格式" value={hxgPrintMode}
                  disabled={generating || merging}
                  className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-neutral-800"
                  onChange={(e) => onFilterChange(() => setHxgPrintMode(e.target.value))}>
                  <option value="auto">按客户自动</option>
                  <option value="preprinted">套打（不带抬头及表头）</option>
                  <option value="full">完整格式</option>
                </select>
                <span className="text-neutral-500">自动模式逐客户选择：思信/迪奇/彩星/迪士尼/buzz/EDU使用预印纸套打，其余客户使用完整格式。套打按《大陆格式.xls》保留实际合同号、票号、日期及业务数据，不重复打印公司和买方抬头、字段名称与明细列标题。</span>
              </div>
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
                        <td className="px-3 py-1.5 font-mono text-xs">华兴_{g.label.replace(/[\\/:*?"<>|]/g, '_')}发票.xlsx</td>
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

        <p className="text-xs text-neutral-400">
          迪奇无样票（借彩星版式、Less 按记录比率反推）、SHU SHU PAPA 70% 票（×0.7×0.967）、国际/贸易簿货款票按 ×0.967 生成（样票是不打折模款票）、EDU 无抬头单元格、一票多合同号只写第一个、思信 5%/其它款/模款票型未自动接线等特殊情况都在上方警告里逐条列出，照常生成但请人工核对。
        </p>
      </div>
    </div>
  )
}
