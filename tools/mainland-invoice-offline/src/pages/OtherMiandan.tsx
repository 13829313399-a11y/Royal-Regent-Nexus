/* eslint-disable */
// @ts-nocheck
import { useEffect, useMemo, useRef, useState } from 'react'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { MonthWarnings } from '@/components/MonthWarnings.tsx'
import { loadAsset } from '@/lib/loadAsset.js'
import { normRange, inRangeYmd, ymdOfParts } from '@/lib/dateRange.js'
import { TPL_FILE } from '@/lib/miandan.js'
import { parseDetailMiandan, generateDetailMiandan } from '@/lib/detailMiandan.js'

const money = (v) => Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const cardCls = 'rounded-xl border-neutral-200 shadow-sm'

export default function OtherMiandan({ incomingSources = [] }) {
  const [tpl, setTpl] = useState(null)
  const [sources, setSources] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(new Set())
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const fileRef = useRef(null)
  const revision = useRef(0)
  const receivedCount = useRef(0)
  const range = useMemo(() => normRange(dateFrom, dateTo), [dateFrom, dateTo])
  const clearResult = () => { revision.current++; setResult(null); setError('') }

  useEffect(() => {
    let active = true
    loadAsset(TPL_FILE).then((b) => { if (active) setTpl(b) }).catch((e) => { if (active) setError(`模板加载失败：${e.message}`) })
    return () => { active = false; revision.current++ }
  }, [])

  const addSource = (source) => {
    setSources((prev) => [...prev.filter((s) => s.name !== source.name), source])
    setSelectedGroups((prev) => new Set([...prev, ...source.parsed.groups.map((g) => g.key)]))
  }

  useEffect(() => {
    const pending = incomingSources.slice(receivedCount.current)
    if (!pending.length) return
    receivedCount.current = incomingSources.length
    clearResult()
    for (const source of pending) {
      if (source.parsed) addSource(source)
      else setSources((prev) => prev.filter((s) => s.name !== source.name))
    }
  }, [incomingSources])

  const upload = async (files) => {
    if (!files?.length || busy) return
    clearResult(); setBusy(true)
    const failures = []
    try {
      for (const file of Array.from(files)) {
        try {
          if (!/\.xlsx$/i.test(file.name)) throw new Error('请上传 .xlsx 出货明细表')
          await new Promise((resolve) => setTimeout(resolve, 20))
          const parsed = await parseDetailMiandan(await file.arrayBuffer(), file.name)
          addSource({ name: file.name, parsed })
        } catch (e) {
          setSources((prev) => prev.filter((s) => s.name !== file.name))
          failures.push(`${file.name}：${e.message || e}`)
        }
      }
    } finally { setBusy(false); setError(failures.join('；')) }
  }

  const groups = useMemo(() => {
    const map = new Map()
    for (const source of sources) for (const group of source.parsed.groups) {
      if (!map.has(group.key)) map.set(group.key, { ...group, byKey: new Map() })
      for (const row of group.rows) map.get(group.key).byKey.set(row.key || row.inv, row)
    }
    return [...map.values()].map((g) => ({ ...g, rows: [...g.byKey.values()].filter((r) => r.date && inRangeYmd(ymdOfParts(r.date), range)) }))
  }, [sources, range.active, range.lo, range.hi])
  const selectedRows = groups.filter((g) => selectedGroups.has(g.key)).flatMap((g) => g.rows)
  const warnings = sources.flatMap((s) => s.parsed.warnings || [])

  const generate = async () => {
    if (!tpl || !selectedRows.length) return
    clearResult(); setGenerating(true)
    const current = revision.current
    await new Promise((resolve) => setTimeout(resolve, 20))
    try {
      const output = await generateDetailMiandan({ tplBuffer: tpl, parsedList: sources.map((s) => s.parsed), dateRange: range, selectedGroups })
      if (current === revision.current) setResult(output)
    } catch (e) { if (current === revision.current) setError(e.message || String(e)) }
    finally { setGenerating(false) }
  }

  const download = () => {
    if (!result) return
    const url = URL.createObjectURL(new Blob([result.buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
    const a = document.createElement('a')
    a.href = url; a.download = '兴信其他客大陆面单.xlsx'; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
    <div className="border-b border-neutral-200 bg-white">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="text-xs tracking-widest text-teal-700">兴信 · 其他客</p>
        <h1 className="mt-2 text-2xl font-semibold">出货明细表生成面单</h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">上传《2026年出货明细表.xlsx》，按客户及出货／费用类别、月份生成香港与大陆金额对照面单。大陆金额与“其他客发票”采用相同规则，保留各客的折率、全价和分期口径。</p>
      </div>
    </div>
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
      <Card className={cardCls}>
        <CardHeader>
          <CardTitle className="text-base">1　上传出货明细表</CardTitle>
          <CardDescription>支持多文件，重复的相同记录只保留一次；同票金额或日期冲突时会提示选择正确版本。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-teal-700"><FileSpreadsheet className="h-4 w-4" />其他客面单模板{tpl ? '（内置）' : '（加载中…）'}</div>
          <button type="button" disabled={busy || generating} className="flex h-32 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-teal-300 bg-teal-50/30 text-sm text-neutral-600 disabled:opacity-50" onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (!generating) upload(e.dataTransfer.files) }}>
            <Upload className="h-5 w-5" />{busy ? '正在解析出货明细表…' : '点击选择或拖拽出货明细表到这里'}
            <span className="text-xs text-neutral-400">.xlsx，可多选</span>
          </button>
          <input ref={fileRef} type="file" accept=".xlsx" multiple hidden aria-label="出货明细表面单上传" onChange={(e) => { upload(e.target.files); e.target.value = '' }} />
          {sources.map((s) => <div key={s.name} className="flex items-center justify-between gap-3 text-sm text-teal-800"><span>{s.name} · 已识别 {s.parsed.groups.reduce((n, g) => n + g.rows.length, 0)} 张</span><Button variant="ghost" size="sm" disabled={busy || generating} onClick={() => { clearResult(); setSources((prev) => prev.filter((x) => x.name !== s.name)) }}>移除</Button></div>)}
          {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        </CardContent>
      </Card>
      {sources.length > 0 && <Card className={cardCls}>
        <CardHeader><CardTitle className="text-base">2　选择客户与日期</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-sm"><label htmlFor="detail-date-from">发票日期</label><Input id="detail-date-from" aria-label="其他客面单开始日期" type="date" className="w-44" value={dateFrom} onChange={(e) => { clearResult(); setDateFrom(e.target.value) }} /><span>至</span><Input aria-label="其他客面单结束日期" type="date" className="w-44" value={dateTo} onChange={(e) => { clearResult(); setDateTo(e.target.value) }} /><span className="text-xs text-neutral-400">留空不限</span></div>
          <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => { clearResult(); setSelectedGroups(new Set(groups.map((g) => g.key))) }}>全选客户</Button><Button variant="outline" size="sm" onClick={() => { clearResult(); setSelectedGroups(new Set()) }}>清空客户</Button></div>
          <div className="overflow-auto rounded-lg border border-neutral-200"><table className="w-full text-sm"><thead className="bg-neutral-50 text-xs text-neutral-500"><tr>{['选择', '客户／来源', '票数', '源金额 USD', '大陆金额 USD'].map((h) => <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>)}</tr></thead><tbody>
            {groups.map((g) => <tr key={g.key} className="border-t border-neutral-100"><td className="px-3 py-2"><input aria-label={`选择${g.label}`} type="checkbox" checked={selectedGroups.has(g.key)} onChange={(e) => { clearResult(); setSelectedGroups((prev) => { const next = new Set(prev); e.target.checked ? next.add(g.key) : next.delete(g.key); return next }) }} /></td><td className="px-3 py-2">{g.label}</td><td className="px-3 py-2">{g.rows.length}</td><td className="px-3 py-2 tabular-nums">{money(g.rows.reduce((s, r) => s + r.sourceTotal, 0))}</td><td className="px-3 py-2 tabular-nums">{money(g.rows.reduce((s, r) => s + r.mainlandTotal, 0))}</td></tr>)}
          </tbody></table></div>
          <div className="max-h-64 overflow-auto"><MonthWarnings items={warnings} range={range} inactiveMode="all" /></div>
        </CardContent>
      </Card>}
      {result && <Card className={cardCls}>
        <CardHeader><CardTitle className="text-base">生成结果</CardTitle><CardDescription>按来源分别列示，香港及大陆金额独立计算；港币换算与每月合计保留公式。</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-teal-800">已生成 {result.sheets.length} 张面单表，{result.sheets.every((s) => !s.selfCheck.fails.length) ? '金额及公式自检通过' : '存在自检差异，请检查下方提示'}</p>
          {result.sheets.map((s) => <div key={s.name} className="text-sm">{s.name} · {s.blocks.reduce((n, b) => n + b.rows, 0)} 张发票 · {s.blocks.length} 个月份块</div>)}
          {result.warnings?.length > 0 && <div className="max-h-40 overflow-auto text-xs text-amber-700">{result.warnings.map((w, i) => <p key={i}>{typeof w === 'string' ? w : w.text}</p>)}</div>}
          <Button onClick={download} disabled={result.sheets.some((s) => s.selfCheck.fails.length)}>下载其他客面单</Button>
        </CardContent>
      </Card>}
    </div>
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-neutral-200 bg-white/95 px-6 py-3"><div className="mx-auto flex max-w-6xl items-center gap-4"><div className="text-sm text-neutral-600">已选 <b>{selectedRows.length}</b> 张 · 大陆金额 <b>{money(selectedRows.reduce((s, r) => s + r.mainlandTotal, 0))}</b> USD</div><Button className="ml-auto bg-teal-700 hover:bg-teal-800" disabled={!tpl || !selectedRows.length || busy || generating} onClick={generate}>{generating ? '生成中…' : '生成其他客面单'}</Button></div></div>
  </div>
}
