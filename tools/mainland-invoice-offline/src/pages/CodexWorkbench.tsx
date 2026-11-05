// @ts-nocheck
import { useEffect, useMemo, useRef, useState } from 'react'
import JSZip from 'jszip'
import { ArrowDownToLine, ArrowRight, Check, CheckCircle2, ChevronLeft, ChevronRight, ClipboardList, Clock3, Download, FileSpreadsheet, FileUp, FolderOpen, LayoutDashboard, ListChecks, LoaderCircle, Plus, Search, Trash2, TriangleAlert, Upload, X } from 'lucide-react'
import { sourceRowsForRecord } from '@/lib/codexImport.js'
import { parseCodexOffThread, cancelCodexParsing } from '@/lib/codexOffThread.js'
import { generateCodexOutputs, buildCodexAuditCsv } from '@/lib/codexExport.js'
import { loadAsset } from '@/lib/loadAsset.js'
import { HddTabColorLegend } from '@/components/HddTabColorLegend'

const KINDS = { hdd: '华登', hxg: '华兴', hka: '华康A', hkb: '华康B', hkd: '华康D', detail: '兴信 · 其他客', zuru: '兴信 · ZURU' }
const NAV = [{ key: 'overview', title: '工作台', icon: LayoutDashboard }, { key: 'imports', title: '资料导入', icon: FileUp }, { key: 'records', title: '发票与追溯', icon: FileSpreadsheet }, { key: 'issues', title: '异常核对', icon: ListChecks }, { key: 'exports', title: '生成与下载', icon: ArrowDownToLine }]
const REVIEW_KEY = 'codex-invoice-review-v1'
const money = (value) => value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'
const safeText = (v) => v === null || v === undefined ? '—' : v instanceof Date ? v.toLocaleDateString('zh-CN') : String(v)
const downloadBuffer = (buffer, name, type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') => {
  const url = URL.createObjectURL(new Blob([buffer], { type }))
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
const readReviews = () => { try { return JSON.parse(localStorage.getItem(REVIEW_KEY) || '{}') } catch { return {} } }

export default function CodexWorkbench() {
  const [view, setView] = useState('overview')
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [resolutions, setResolutions] = useState(readReviews)
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('all')
  const [issueFilter, setIssueFilter] = useState('pending')
  const [issueQuery, setIssueQuery] = useState('')
  const [issuePage, setIssuePage] = useState(1)
  const [recordStatus, setRecordStatus] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [outputs, setOutputs] = useState(null)
  const [exporting, setExporting] = useState(false)
  const [hxgPrintMode, setHxgPrintMode] = useState('auto')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)
  const revision = useRef(0)

  useEffect(() => { try { localStorage.setItem(REVIEW_KEY, JSON.stringify(resolutions)) } catch { setNotice('本次核对结论仅在当前页面保留，可下载核对记录备份。') } }, [resolutions])
  useEffect(() => { const key = (e) => { if (e.key === 'Escape') setDetail(null) }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key) }, [])
  useEffect(() => { setPage(1) }, [query, kind, recordStatus, from, to])
  useEffect(() => { setIssuePage(1) }, [issueQuery, issueFilter])

  const records = useMemo(() => sessions.flatMap((s) => (s.records || []).map((r) => ({ ...r, session: s }))), [sessions])
  const issues = useMemo(() => sessions.flatMap((s) => (s.issues || []).map((i) => ({ ...i, session: s }))), [sessions])
  const byRecord = useMemo(() => { const m = new Map(); for (const i of issues) for (const id of new Set([i.recordId, ...(i.recordIds || [])].filter(Boolean))) { if (!m.has(id)) m.set(id, []); m.get(id).push(i) } return m }, [issues])
  const reviewStatus = (i) => resolutions[i.id]?.status || 'open'
  const statusOf = (r) => {
    const relevant = (byRecord.get(r.id) || []).filter((i) => i.severity !== 'info')
    if (!relevant.length) return 'normal'
    if (relevant.some((i) => reviewStatus(i) === 'open')) return 'open'
    if (relevant.some((i) => reviewStatus(i) === 'deferred')) return 'deferred'
    return 'reviewed'
  }
  const pending = issues.filter((i) => i.severity !== 'info' && reviewStatus(i) !== 'reviewed')
  const selectedRecords = records.filter((r) => selected.has(r.id))
  const totals = (list) => Object.entries(list.reduce((out, r) => { if (Number.isFinite(r.amount)) { const cents = Math.sign(r.amount) * Math.round((Math.abs(r.amount) + Number.EPSILON * Math.max(1, Math.abs(r.amount))) * 100); out[r.currency || '未注明币种'] = (out[r.currency || '未注明币种'] || 0) + cents } return out }, {})).map(([currency, cents]) => [currency, cents / 100])
  const filtered = useMemo(() => records.filter((r) => (kind === 'all' || r.session.kind === kind)
    && (!query.trim() || `${r.invNo} ${r.customer} ${r.session.name} ${r.sourceSheet}`.toLowerCase().includes(query.trim().toLowerCase()))
    && (!from || r.date >= from) && (!to || (!!r.date && r.date <= to))
    && (recordStatus === 'all' || statusOf(r) === recordStatus)), [records, kind, query, from, to, recordStatus, resolutions, byRecord])
  const pageCount = Math.max(1, Math.ceil(filtered.length / 40))
  const actualPage = Math.min(page, pageCount)
  const pageRows = filtered.slice((actualPage - 1) * 40, actualPage * 40)
  const shownIssues = issues.filter((i) => (issueFilter === 'all' || (issueFilter === 'reviewed' ? reviewStatus(i) === 'reviewed' : i.severity !== 'info' && reviewStatus(i) !== 'reviewed')) && (!issueQuery.trim() || `${i.invNo} ${i.text} ${i.sheet} ${i.session.name}`.toLowerCase().includes(issueQuery.trim().toLowerCase())))
  const issuePages = Math.max(1, Math.ceil(shownIssues.length / 40))
  const actualIssuePage = Math.min(issuePage, issuePages)
  const canMiandan = selectedRecords.length > 0 && selectedRecords.every((r) => ['hdd', 'detail', 'zuru'].includes(r.session.kind))
  const invalidate = () => { revision.current++; setOutputs(null); setError('') }

  const acceptSession = (session, demo = false) => {
    const value = { ...session, demo }
    setSessions((prev) => [...prev.filter((s) => s.id !== value.id && s.name !== value.name), value])
    setSelected((prev) => new Set([...prev, ...(value.records || []).map((r) => r.id)]))
  }
  useEffect(() => {
    const ids = new Set(records.map((r) => r.id))
    setSelected((prev) => new Set([...prev].filter((id) => ids.has(id))))
  }, [records])

  const importFiles = async (files, demo = false) => {
    if (!files?.length || busy || exporting) return
    invalidate(); setNotice(''); setBusy(true)
    const token = revision.current
    const failures = []
    setView('imports')
    for (let index = 0; index < files.length; index++) {
      if (token !== revision.current) break
      const file = files[index]
      setProgress(`正在识别 ${index + 1}/${files.length} · ${file.name}`)
      setSessions((prev) => prev.filter((s) => s.name !== file.name))
      try {
        const buffer = file.buffer || await file.arrayBuffer()
        if (token !== revision.current) break
        const session = await parseCodexOffThread(file.name, buffer, file.kind || 'auto')
        if (token !== revision.current) break
        acceptSession(session, demo)
      } catch (e) { if (e.name !== 'AbortError') failures.push(`${file.name}：${e.message || e}`) }
    }
    if (token === revision.current) { setBusy(false); setProgress(''); setError(failures.join('；')); if (!failures.length) setNotice('资料已导入。可进入“发票与追溯”查看每张票，或先处理待核对提示。') }
  }
  const loadDemo = async () => {
    if (busy || exporting) return
    invalidate(); setBusy(true); setProgress('正在载入现有资料演示…')
    const token = revision.current
    try {
      const specs = [ ['华登票记录.xlsx', 'hdd'], ['华兴SHUSHUPAPA排期.xlsx', 'hxg'], ['2026年出货明细表.xlsx', 'detail'] ]
      const files = []
      for (const [name, kind] of specs) { const buffer = await loadAsset(`/codex-demo/${name}`); if (token !== revision.current) return; files.push({ name, kind, buffer }) }
      if (token !== revision.current) return
      setBusy(false)
      // 本函数闭包进入时 busy=false，可继续交给统一导入。
      await importFiles(files, true)
    } catch (e) { if (token === revision.current) { setBusy(false); setProgress(''); setError(e.message || String(e)) } }
  }
  const cancelImport = () => { revision.current++; cancelCodexParsing(); setBusy(false); setProgress(''); setNotice('本次导入已取消，已完成的文件仍保留。') }
  const chooseType = async (session, choice) => {
    if (!choice || busy || exporting) return
    invalidate(); setBusy(true); setProgress(`按${KINDS[choice]}重新识别…`)
    const token = revision.current
    try { const result = await parseCodexOffThread(session.name, session.originalBuffer || session.buffer, choice); if (token === revision.current) acceptSession(result, session.demo) }
    catch (e) { if (e.name !== 'AbortError' && token === revision.current) setError(e.message || String(e)) }
    finally { if (token === revision.current) { setBusy(false); setProgress('') } }
  }
  const remove = (session) => { invalidate(); setSessions((prev) => prev.filter((s) => s.id !== session.id)); if (detail?.session.id === session.id) setDetail(null) }
  const toggle = (id, checked) => { if (busy || exporting) return; invalidate(); setSelected((prev) => { const next = new Set(prev); checked ? next.add(id) : next.delete(id); return next }) }
  const selectVisible = (checked) => { if (busy || exporting) return; invalidate(); setSelected((prev) => { const next = new Set(prev); for (const r of filtered) checked ? next.add(r.id) : next.delete(r.id); return next }) }
  const exportData = async (type) => {
    if (!selectedRecords.length || busy || exporting) return
    setExporting(true); setError(''); setProgress('正在准备生成…')
    const token = revision.current
    try {
      const result = await generateCodexOutputs(sessions, { selectedRecordIds: new Set(selected), outputType: type, hxgPrintMode, onProgress: (message) => setProgress(typeof message === 'string' ? message : message?.message || '正在生成文件…') })
      if (token !== revision.current) return
      setSessions((prev) => prev.map((s) => ({ ...s, records: [...s.records] })))
      setOutputs({ ...result, type, createdAt: new Date().toLocaleString('zh-CN'), selectedCount: selectedRecords.length }); setView('exports')
    } catch (e) { setError(e.message || String(e)) }
    finally { setExporting(false); setProgress('') }
  }
  const downloadAudit = async () => {
    try { const csv = await buildCodexAuditCsv(sessions, selected, resolutions); downloadBuffer(csv, 'codex版_核对记录.csv', 'text/csv;charset=utf-8') }
    catch (e) { setError(e.message || String(e)) }
  }
  const downloadZip = async () => {
    if (!outputs?.files.length) return
    const zip = new JSZip()
    for (const f of outputs.files) zip.file(f.name, f.buffer)
    zip.file('codex版_核对记录.csv', await buildCodexAuditCsv(sessions, selected, resolutions))
    downloadBuffer(await zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' }), 'codex版_生成结果.zip', 'application/zip')
  }

  const UploadBox = ({ compact = false }) => <div className={`cx-upload ${compact ? 'compact' : ''} ${dragging ? 'dragging' : ''}`} onDragOver={(e) => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); importFiles(Array.from(e.dataTransfer.files)) }}>
    <span className="cx-upload-icon"><Upload size={24} /></span><h3>把资料拖到这里</h3><p>发票记录、客户排期表、出货明细、ZURU 发票簿</p><button className="cx-button primary" disabled={busy || exporting} onClick={() => inputRef.current?.click()}><Plus size={16} />选择文件</button><small>支持 Excel 文件，可一次导入多份 · 在本机识别</small>
  </div>
  const FilesList = () => <section className="cx-card"><div className="cx-section-heading"><div><h2>已导入资料 <span>{sessions.length}</span></h2><p>识别依据、来源及处理状态都保留在这里。</p></div><button className="cx-button subtle" disabled={busy || exporting} onClick={() => inputRef.current?.click()}><Plus size={15} />继续导入</button></div>
    {!sessions.length ? <Empty icon={FolderOpen} title="还没有导入资料" text="上传你的文件，或载入现有资料演示。" /> : <div className="cx-file-list">{sessions.map((s) => <div className="cx-file-row" key={s.id}><span className="cx-file-icon"><FileSpreadsheet size={22} /></span><div className="cx-file-info"><strong>{s.name}</strong><div><span className={`cx-pill ${s.status === 'ready' ? 'green' : 'amber'}`}>{s.status === 'ready' ? KINDS[s.kind] || s.label : '待选择类型'}</span>{s.demo && <span className="cx-pill gray">现有资料演示</span>}<small>{s.records.length} 张发票 · {s.issues.length} 条提示</small></div>{s.status === 'needs-type' && <p>{s.candidates?.map((c) => `${c.label}：${c.reason}`).join('；') || '现有信息不足以确定来源，请选择资料类型。'}</p>}</div>{s.status === 'needs-type' ? <select aria-label={`选择${s.name}资料类型`} defaultValue="" disabled={busy || exporting} onChange={(e) => chooseType(s, e.target.value)}><option value="" disabled>选择资料类型</option>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select> : <button className="cx-button subtle" onClick={() => { setKind(s.kind); setQuery(s.name); setView('records') }}>查看发票<ChevronRight size={15} /></button>}<button className="cx-icon-button" aria-label={`移除${s.name}`} disabled={busy || exporting} onClick={() => remove(s)}><Trash2 size={16} /></button></div>)}</div>}
  </section>
  const HxgPrintOptions = () => selectedRecords.some((r) => r.session.kind === 'hxg') && <section className="cx-card"><div className="cx-filter-row"><label htmlFor="cx-hxg-print-mode">华兴打印格式</label><select id="cx-hxg-print-mode" aria-label="华兴打印格式" value={hxgPrintMode} disabled={busy || exporting} onChange={(e) => { invalidate(); setHxgPrintMode(e.target.value) }}><option value="auto">按客户自动</option><option value="preprinted">套打（不带抬头及表头）</option><option value="full">完整格式</option></select></div><p className="cx-filter-row secondary">套打保留实际合同号、票号、日期及业务数据，不重复打印公司和买方抬头、字段名称与明细列标题。</p></section>
  const ExportActions = () => <div className="cx-export-actions"><button className="cx-button primary" disabled={!selectedRecords.length || busy || exporting} onClick={() => exportData('invoice')}><FileSpreadsheet size={16} />生成发票 Excel</button><button className="cx-button" disabled={!canMiandan || busy || exporting} title={canMiandan ? '' : '面单支持华登、兴信其他客及ZURU，请选择对应资料的发票'} onClick={() => exportData('miandan')}>生成面单 Excel</button><button className="cx-button" disabled={!selectedRecords.length || busy || exporting} onClick={downloadAudit}><ClipboardList size={16} />下载核对记录</button></div>

  return <div className="codex-workbench">
    <input ref={inputRef} hidden multiple type="file" accept=".xlsx,.xls,.xlsm,.et" aria-label="codex导入资料" onChange={(e) => { importFiles(Array.from(e.target.files || [])); e.target.value = '' }} />
    <aside className="cx-sidebar"><div className="cx-brand"><span className="cx-brand-icon">c<span>›</span></span><div><strong>大陆发票系统</strong><span className="cx-brand-edition">codex版</span></div></div><p className="cx-nav-label">工作空间</p><nav>{NAV.map(({ key, title, icon: Icon }) => <button key={key} className={view === key ? 'active' : ''} onClick={() => setView(key)}><Icon size={18} /><span>{title}</span>{key === 'issues' && pending.length > 0 && <b>{pending.length}</b>}</button>)}</nav><div className="cx-side-note"><div className="cx-dot" />本机离线运行<p>资料解析和文件生成<br />均在当前电脑完成</p></div><div className="cx-sidebar-footer"><span>codex版 · 预览版 01</span><small>2026.10.28</small></div></aside>
    <div className="cx-body"><header className="cx-header"><div><span>工作空间</span><ChevronRight size={14} /><strong>{NAV.find((n) => n.key === view)?.title}</strong></div><div><span className="cx-local-label"><span className="cx-dot" />离线可用</span><button className="cx-button small" disabled={busy || exporting} onClick={() => inputRef.current?.click()}><Plus size={15} />导入资料</button></div></header>
      <main className="cx-main">
        {(busy || exporting) && <div className="cx-progress" role="status"><LoaderCircle className="cx-spin" size={18} /><span>{progress}</span>{busy && <button onClick={cancelImport}>取消导入</button>}</div>}
        {error && <div className="cx-message error" role="alert"><TriangleAlert size={18} /><span>{error}</span><button aria-label="关闭错误提示" onClick={() => setError('')}><X size={16} /></button></div>}
        {notice && <div className="cx-message"><CheckCircle2 size={18} /><span>{notice}</span><button aria-label="关闭消息" onClick={() => setNotice('')}><X size={16} /></button></div>}

        {view === 'overview' && <>
          <section className="cx-hero"><div><span className="cx-eyebrow">CODEX / INVOICE WORKSPACE</span><h1>每张发票，都有来处。</h1><p>导入资料、核对异常、追溯原行，再生成发票与面单。<br />熟悉的票面格式，集中在一个工作台。</p><div className="cx-hero-actions"><button className="cx-button primary" disabled={busy || exporting} onClick={() => inputRef.current?.click()}><Upload size={17} />导入资料<ArrowRight size={17} /></button><button className="cx-button" disabled={busy || exporting} onClick={loadDemo}>载入现有资料演示</button></div><small>演示使用现有华登、华兴及其他客原表，可移除或换成最新资料。</small></div><div className="cx-flow-card"><div className="cx-flow-step"><span>01</span><div><strong>识别资料</strong><small>识别厂区与资料类型</small></div><Check size={16} /></div><div className="cx-flow-step"><span>02</span><div><strong>核对与追溯</strong><small>查看源行，记录处理结论</small></div><ListChecks size={16} /></div><div className="cx-flow-step"><span>03</span><div><strong>生成文件</strong><small>发票 · 面单 · 核对记录</small></div><Download size={16} /></div></div></section>
          <div className="cx-stats"><Stat title="导入资料" value={sessions.length} unit="份" icon={FolderOpen} detail="当前工作空间" /><Stat title="识别发票" value={records.length} unit="张" icon={FileSpreadsheet} detail="支持逐票查看来源" /><Stat title="待核对提示" value={pending.length} unit="条" icon={TriangleAlert} accent={pending.length > 0} detail="含暂留待核对事项" /><Stat title="已生成文件" value={outputs?.files.length || 0} unit="个" icon={Download} detail={outputs ? '可在生成与下载中领取' : '选择发票后生成'} /></div>
          <div className="cx-overview-grid"><section className="cx-card"><div className="cx-section-heading"><div><h2>厂区与资料</h2><p>沿用已验收的计算规则和票面模板。</p></div></div><div className="cx-modules">{Object.entries(KINDS).map(([key, label]) => { const count = records.filter((r) => r.session.kind === key).length; return <button key={key} onClick={() => { setKind(key); setQuery(''); setView(count ? 'records' : 'imports') }}><span className="cx-module-mark">{label.startsWith('兴信') ? '兴' : label.slice(0, 2)}</span><div><strong>{label}</strong><small>{count ? `${count} 张已导入` : '可导入资料'}</small></div><ChevronRight size={16} /></button> })}</div></section><section className="cx-card cx-next"><span className="cx-eyebrow">下一步</span><h2>{records.length ? pending.length ? '先看看待核对事项' : '查看发票，准备生成' : '从一份真实资料开始'}</h2><p>{records.length ? '每个提示都保留文件、票号与来源位置。填写核对结论后，可以随生成结果一起导出。' : '支持多份文件一起上传。识别不确定时会列出依据，让你选择正确的资料类型。'}</p><button className="cx-button" onClick={() => setView(records.length ? pending.length ? 'issues' : 'records' : 'imports')}>{records.length ? pending.length ? '进入异常核对' : '查看发票' : '进入资料导入'}<ArrowRight size={16} /></button><div className="cx-next-note"><Clock3 size={16} /><span>核对结论按文件版本保存在当前浏览器。</span></div></section></div>
          <FilesList />
        </>}

        {view === 'imports' && <><PageTitle eyebrow="IMPORT" title="资料只需导入一次" text="按文件内容和工作表识别来源；不确定的资料由你选择类型。" /><UploadBox /><FilesList /><p className="cx-footnote">也可以<button onClick={loadDemo} disabled={busy || exporting}>载入现有资料演示</button>，体验逐票追溯与生成。</p></>}

        {view === 'records' && <><PageTitle eyebrow="INVOICES" title="发票与来源，一起核对" text="点击票号查看原文件、工作表、源行和计价明细。" /><section className="cx-card cx-records-card"><div className="cx-filter-row"><div className="cx-search"><Search size={17} /><input aria-label="搜索发票" placeholder="搜索票号、客户、文件名…" value={query} onChange={(e) => setQuery(e.target.value)} /></div><select aria-label="筛选厂区" value={kind} onChange={(e) => setKind(e.target.value)}><option value="all">所有厂区 / 资料</option>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><select aria-label="筛选核对状态" value={recordStatus} onChange={(e) => setRecordStatus(e.target.value)}><option value="all">全部核对状态</option><option value="open">需核对</option><option value="deferred">已暂留</option><option value="reviewed">已核对</option><option value="normal">无待核对提示</option></select></div><div className="cx-filter-row secondary"><span>发票日期</span><input type="date" aria-label="开始日期" value={from} onChange={(e) => setFrom(e.target.value)} /><span>至</span><input type="date" aria-label="结束日期" value={to} onChange={(e) => setTo(e.target.value)} /><button className="cx-text-button" onClick={() => { setQuery(''); setKind('all'); setRecordStatus('all'); setFrom(''); setTo('') }}>重置筛选</button><span className="cx-filter-count">显示 {filtered.length} 张</span></div>
          <div className="cx-selection-row"><div><button onClick={() => selectVisible(true)} disabled={busy || exporting}>选中筛选结果</button><span> / </span><button onClick={() => selectVisible(false)} disabled={busy || exporting}>取消筛选结果</button><span className="cx-selected-count">共选中 {selectedRecords.length} 张</span></div><button className="cx-text-button" disabled={busy || exporting} onClick={() => { invalidate(); setSelected(new Set()) }}>清空选择</button></div>
          <div className="cx-table-wrap"><table className="cx-table"><thead><tr><th className="cx-check-col">选择</th><th>发票号码</th><th>客户 / 厂区</th><th>日期</th><th className="right">生成金额</th><th>核对状态</th><th>来源</th></tr></thead><tbody>{pageRows.map((r) => <tr key={r.id}><td><input type="checkbox" disabled={busy || exporting} aria-label={`选择发票${r.invNo}`} checked={selected.has(r.id)} onChange={(e) => toggle(r.id, e.target.checked)} /></td><td><button className="cx-invoice-link" onClick={() => setDetail(r)}>{r.invNo}<ChevronRight size={14} /></button></td><td><strong>{r.customer || '未注明客户'}</strong><small>{KINDS[r.session.kind]}</small></td><td>{r.date || <span className="cx-warning-text">缺日期</span>}</td><td className="right cx-number"><strong>{money(r.amount)}</strong>{r.amount === null && <small>{r.amountLabel || '生成后核对'}</small>}<small>{r.currency || '币种待核对'}</small></td><td><RecordBadge status={statusOf(r)} /></td><td><button className="cx-source-link" title={r.session.name} onClick={() => setDetail(r)}>{r.sourceSheet || r.session.name}<small>{r.sourceRows?.length ? `第 ${r.sourceRows.slice(0, 3).join('、')} 行${r.sourceRows.length > 3 ? '…' : ''}` : '查看源工作表'}</small></button></td></tr>)}</tbody></table></div>{!pageRows.length && <Empty icon={Search} title={records.length ? '没有符合筛选的发票' : '导入后，发票会显示在这里'} text={records.length ? '可以调整搜索条件或日期范围。' : '先到资料导入，上传记录或载入现有资料演示。'} />}
          <div className="cx-pagination"><span>每页 40 张 · 第 {actualPage} / {pageCount} 页</span><div><button className="cx-icon-button" aria-label="上一页" disabled={actualPage <= 1} onClick={() => setPage(actualPage - 1)}><ChevronLeft size={18} /></button><button className="cx-icon-button" aria-label="下一页" disabled={actualPage >= pageCount} onClick={() => setPage(actualPage + 1)}><ChevronRight size={18} /></button></div></div></section><HxgPrintOptions /><section className="cx-selection-summary"><div><strong>本次选中 {selectedRecords.length} 张</strong><p>{totals(selectedRecords).map(([c, n]) => `${c} ${money(n)}`).join('　') || '按币种分别汇总'}{selectedRecords.some((r) => r.amount === null) && ` · ${selectedRecords.filter((r) => r.amount === null).length} 张金额待生成后核对`}</p></div><ExportActions /></section>{!canMiandan && selectedRecords.length > 0 && <p className="cx-footnote">面单生成支持华登、兴信其他客与 ZURU。选择对应资料的发票后即可使用。</p>}</>}

        {view === 'issues' && <><PageTitle eyebrow="REVIEW" title="把异常，核对清楚" text="保留系统提示，记录处理结论；核对状态不会修改原表或改变发票金额。" /><section className="cx-card"><div className="cx-section-heading"><div className="cx-segments">{[['pending', '待核对'], ['reviewed', '已核对'], ['all', '全部提示']].map(([k, label]) => <button className={issueFilter === k ? 'active' : ''} key={k} onClick={() => setIssueFilter(k)}>{label}</button>)}</div><button className="cx-button small" disabled={!selectedRecords.length} onClick={downloadAudit}><Download size={15} />下载所选票核对记录</button></div><div className="cx-filter-row"><div className="cx-search"><Search size={17} /><input aria-label="搜索核对提示" placeholder="搜索票号、来源或提示内容…" value={issueQuery} onChange={(e) => setIssueQuery(e.target.value)} /></div><span className="cx-filter-count">{shownIssues.length} 条提示</span>{issueQuery && <button className="cx-text-button" onClick={() => setIssueQuery('')}>清空搜索</button>}</div><div className="cx-issue-list">{shownIssues.slice((actualIssuePage - 1) * 40, actualIssuePage * 40).map((i) => <IssueCard key={i.id} issue={i} resolution={resolutions[i.id]} onSave={(status, note) => setResolutions((prev) => ({ ...prev, [i.id]: { status, note, updatedAt: new Date().toISOString() } }))} onLocate={() => { const r = records.find((r) => r.id === i.recordId); if (r) setDetail(r); else { setQuery(i.session.name); setKind('all'); setView('records') } }} />)}</div>{!shownIssues.length && <Empty icon={CheckCircle2} title={sessions.length ? '这里暂时没有提示' : '导入资料后开始核对'} text="有需要核对的情况时，会显示票号、源文件与定位信息。" />}<div className="cx-pagination"><span>每页 40 条 · 第 {actualIssuePage} / {issuePages} 页</span><div><button className="cx-icon-button" aria-label="提示上一页" disabled={actualIssuePage <= 1} onClick={() => setIssuePage(actualIssuePage - 1)}><ChevronLeft size={18} /></button><button className="cx-icon-button" aria-label="提示下一页" disabled={actualIssuePage >= issuePages} onClick={() => setIssuePage(actualIssuePage + 1)}><ChevronRight size={18} /></button></div></div></section></>}

        {view === 'exports' && <><PageTitle eyebrow="EXPORT" title="生成后，再交付" text="用当前勾选的发票生成 Excel，也可下载带处理结论的核对记录。" /><HxgPrintOptions /><section className="cx-card cx-export-start"><div><h2>已选 {selectedRecords.length} 张发票</h2><p>{totals(selectedRecords).map(([c, n]) => `${c} ${money(n)}`).join('　') || '到“发票与追溯”选择要生成的发票。'}{selectedRecords.some((r) => r.amount === null) && ` · ${selectedRecords.filter((r) => r.amount === null).length} 张金额待生成后核对`}</p></div><ExportActions /></section>{!canMiandan && selectedRecords.length > 0 && <p className="cx-footnote">面单支持华登、兴信其他客与 ZURU 资料。不同来源分别生成对应面单。</p>}{outputs ? <section className="cx-card"><div className="cx-section-heading"><div><h2>生成完成 <span>{outputs.files.length} 个文件</span></h2><p>{outputs.createdAt} · 本次选择 {outputs.selectedCount} 张发票</p></div><button className="cx-button primary" onClick={downloadZip}><Download size={16} />下载整包 ZIP</button></div>{outputs.type === 'invoice' && <HddTabColorLegend customers={selectedRecords.filter((r) => r.session.kind === 'hdd').map((r) => r.customer)} />}<div className="cx-file-list">{outputs.files.map((f, index) => <div key={`${f.name}-${index}`} className="cx-file-row"><span className="cx-file-icon"><FileSpreadsheet size={22} /></span><div className="cx-file-info"><strong>{f.name}</strong><small>{((f.buffer.byteLength || f.buffer.length || 0) / 1024).toFixed(0)} KB · Excel 工作簿</small></div><button className="cx-button small" onClick={() => downloadBuffer(f.buffer, f.name)}><Download size={15} />下载</button></div>)}</div>{outputs.notes?.length > 0 && <div className="cx-output-notes"><strong>本次生成提示</strong>{outputs.notes.map((n, index) => <p key={index}>{typeof n === 'string' ? n : n.text}</p>)}</div>}</section> : <section className="cx-card"><Empty icon={Download} title="生成的文件会保留在这里" text="导入资料并选择发票后，点击上方按钮生成。修改导入资料或勾选范围后需重新生成。" /></section>}</>}
        <footer className="cx-main-footer"><span>大陆发票系统 · codex版</span><span>独立预览版 01 / 2026.10.28</span></footer>
      </main>
    </div>
    {detail && <RecordDrawer record={detail} issues={byRecord.get(detail.id) || []} resolutions={resolutions} onClose={() => setDetail(null)} onReview={() => { setIssueQuery(detail.invNo); setDetail(null); setIssueFilter('all'); setView('issues') }} />}
  </div>
}

function PageTitle({ eyebrow, title, text }) { return <div className="cx-page-title"><span className="cx-eyebrow">{eyebrow}</span><h1>{title}</h1><p>{text}</p></div> }
function Stat({ title, value, unit, icon: Icon, detail, accent }) { return <div className={`cx-stat ${accent ? 'accent' : ''}`}><div><span>{title}</span><Icon size={18} /></div><strong>{value.toLocaleString()}<small>{unit}</small></strong><p>{detail}</p></div> }
function Empty({ icon: Icon, title, text }) { return <div className="cx-empty"><span><Icon size={25} /></span><h3>{title}</h3><p>{text}</p></div> }
function RecordBadge({ status }) { return <span className={`cx-pill ${status === 'open' ? 'amber' : status === 'deferred' ? 'gray' : 'green'}`}>{({ open: '需核对', deferred: '已暂留', reviewed: '已核对', normal: '无待核对提示' })[status]}</span> }
function IssueCard({ issue, resolution, onSave, onLocate }) {
  const [note, setNote] = useState(resolution?.note || '')
  const status = resolution?.status || 'open'
  return <article className="cx-issue"><div className={`cx-issue-icon ${issue.severity}`}><TriangleAlert size={19} /></div><div className="cx-issue-content"><div className="cx-issue-heading"><span className="cx-pill gray">{issue.category || '来源提示'}</span><strong>{issue.invNo || '文件级提示'}</strong><RecordBadge status={status} /></div><p className="cx-issue-description">{issue.text}</p><button className="cx-issue-source" onClick={onLocate}>{issue.session.name}{issue.sheet ? ` / ${issue.sheet}` : ''}{issue.row ? ` / 第 ${issue.row} 行` : ''}<ArrowRight size={13} /></button><div className="cx-issue-controls"><input aria-label={`核对说明${issue.id}`} placeholder="填写核对结论或暂留原因…" value={note} onChange={(e) => setNote(e.target.value)} /><button className="cx-button small" onClick={() => onSave('reviewed', note)}><Check size={14} />标记已核对</button><button className="cx-text-button" onClick={() => onSave('deferred', note)}>暂留</button>{status !== 'open' && <button className="cx-text-button" onClick={() => onSave('open', note)}>重新核对</button>}</div>{resolution?.updatedAt && <small className="cx-review-time">上次处理：{new Date(resolution.updatedAt).toLocaleString('zh-CN')}</small>}</div></article>
}
function RecordDrawer({ record, issues, resolutions, onClose, onReview }) {
  const source = useMemo(() => { try { return sourceRowsForRecord(record.session, record) } catch { return [] } }, [record])
  const lines = record.lines || []
  return <div className="cx-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><aside className="cx-drawer" role="dialog" aria-modal="true" aria-label={`发票${record.invNo}追溯`}><div className="cx-drawer-heading"><div><span className="cx-eyebrow">INVOICE TRACE</span><h2>{record.invNo}</h2><p>{record.customer} · {KINDS[record.session.kind]}</p></div><button className="cx-icon-button" aria-label="关闭追溯" onClick={onClose}><X size={21} /></button></div><div className="cx-drawer-content"><div className="cx-detail-total"><span>{record.amountLabel || '生成金额'}</span><strong>{money(record.amount)} <small>{record.currency}</small></strong><span>{record.date || '日期待补充'}</span></div><section><h3>来源定位</h3><dl className="cx-source-meta"><dt>文件</dt><dd>{record.session.name}</dd><dt>工作表</dt><dd>{record.sourceSheet || '未定位'}</dd><dt>原表行号</dt><dd>{record.sourceRows?.length ? record.sourceRows.join('、') : '未取得精确行号，请查看源工作表'}</dd></dl>{record.sourceNote && <p className="cx-muted">{record.sourceNote}</p>}</section><section><h3>计价明细 <small>{lines.length} 行</small></h3>{lines.length ? <div className="cx-table-wrap"><table className="cx-table cx-line-table"><thead><tr><th>货号 / 描述</th><th>类型</th><th className="right">数量</th><th className="right">原单价</th><th className="right">源金额</th></tr></thead><tbody>{lines.map((l, index) => <tr key={index}><td>{safeText(l.code ?? l.desc ?? l.no ?? l.description ?? l.item ?? '')}</td><td>{({ goods: '货物', item: '货物', mold: '模款', fee: '费用', note: '说明' })[l.kind] || l.kind || '明细'}</td><td className="right">{safeText(l.qty ?? l.quantity)}</td><td className="right">{safeText(l.price ?? l.unit)}</td><td className="right">{safeText(l.amount ?? l.amt ?? l.usd)}</td></tr>)}</tbody></table></div> : <p className="cx-muted">此记录按整票金额读取，原始明细见下方来源。</p>}</section><section><h3>核对提示 <small>{issues.length} 条</small></h3>{issues.length ? <><div className="cx-trace-issues">{issues.map((i) => <div key={i.id}><span className={`cx-pill ${resolutions[i.id]?.status === 'reviewed' ? 'green' : 'amber'}`}>{resolutions[i.id]?.status === 'reviewed' ? '已核对' : resolutions[i.id]?.status === 'deferred' ? '暂留' : '待核对'}</span><p>{i.text}</p>{resolutions[i.id]?.note && <small>核对结论：{resolutions[i.id].note}</small>}</div>)}</div><button className="cx-button small" onClick={onReview}>进入异常核对<ArrowRight size={14} /></button></> : <div className="cx-quiet-check"><CheckCircle2 size={16} />当前解析器未给出逐票提示</div>}</section><section><h3>原表内容</h3><p className="cx-muted">下列地址与内容直接读取自上传的工作簿。</p>{source.length ? <div className="cx-source-rows">{source.map((r) => <div key={r.row}><strong>第 {r.row} 行</strong><div>{r.cells.filter((c) => c.value !== null && c.value !== undefined && c.value !== '').map((c) => <span key={c.address}><b>{c.address}</b>{safeText(c.value)}{c.display && String(c.display) !== safeText(c.value) && <small className="cx-original-format">原格式显示：{c.display}</small>}</span>)}</div></div>)}</div> : <p className="cx-muted">未取得可核实的精确源行，已保留上方源文件和工作表信息。</p>}</section></div></aside></div>
}
