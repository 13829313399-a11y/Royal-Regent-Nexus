import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { rrToolsUrl } from '../runtime/rrIntegration';
import { Icon } from '../icons';
import { activeJob, artifactUrl, canApplyJobPoll, preserveLabel, request, requestId, stageLabel, stateLabel, type Capabilities, type Job, type Options, type Source, type Review } from './api';

type Item = { key: string; name: string; state: string; error?: string; source?: Source; sourceId?: string; job?: Job };
type Box = { x0: number; y0: number; x1: number; y1: number };
const message = (error: unknown) => error instanceof Error ? error.message : '暂时无法处理，请重试。';
const orderedPages = (job: Job | undefined, role: string) => job?.artifacts.filter(a => a.role === role).sort((a, b) => a.filename.localeCompare(b.filename)) ?? [];

export function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState<'work' | 'history'>('work');
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [options, setOptions] = useState<Options>({ translation_direction: 'en_to_zh', translation_engine: 'offline', glossary: '', page_selection: 'all' });
  const [history, setHistory] = useState<Job[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  const [view, setView] = useState<'source' | 'result'>('result');
  const [patching, setPatching] = useState(false);
  const [box, setBox] = useState<Box>();
  const [zoom, setZoom] = useState(1);
  const [review, setReview] = useState<Review>();
  const [reviewFocus, setReviewFocus] = useState<Box>();
  const [password, setPassword] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const dragStart = useRef<{ x: number; y: number }>();
  const latest = useRef(items);
  latest.current = items;
  const controller = useRef(new AbortController());
  const historyPageRef = useRef(historyPage);
  historyPageRef.current = historyPage;
  const pollBusy = useRef(false);
  const firstCapabilities = useRef(true);
  const busyLock = useRef(false);
  const current = items.find(item => item.key === selected);
  const job = current?.job;
  const results = orderedPages(job, 'result_page');
  const sources = orderedPages(job, 'source_page');
  const visiblePage = Math.min(page, Math.max(0, results.length - 1));
  const shown = (view === 'source' ? sources : results)[visiblePage];
  const sourcePreview = current?.source?.artifacts.find(a => a.role === 'preview');
  const ready = items.filter(item => item.state === 'ready' && item.sourceId && !item.job);
  const available = capabilities?.image_translation?.available && (options.translation_engine === 'online' ? capabilities.translation.online_available : capabilities.translation.offline_available);
  const reviewArtifact = job?.artifacts.find(a => a.role === 'translation_review');
  const actualPageIndex = Number(results[visiblePage]?.filename.match(/page-(\d+)/)?.[1] ?? '1') - 1;
  const pageRegions = review?.regions.filter(r => r.page_index === actualPageIndex) ?? [];
  const highlight = patching ? box : reviewFocus;
  useEffect(() => {
    setReview(undefined); setReviewFocus(undefined);
    if (!reviewArtifact) return;
    const abort = new AbortController();
    void request<Review>(`/artifacts/${reviewArtifact.id}/content`, abort.signal).then(value => {
      if (!abort.signal.aborted) setReview(value);
    }).catch(err => { if (!abort.signal.aborted) setError(message(err)); });
    return () => abort.abort();
  }, [reviewArtifact?.id]);
  useEffect(() => { setReviewFocus(undefined); setBox(undefined); }, [selected, visiblePage]);

  function update(key: string, values: Partial<Item>) {
    setItems(old => old.map(item => item.key === key ? { ...item, ...values } : item));
  }
  async function refresh(signal = controller.current.signal) {
    if (pollBusy.current) return;
    pollBusy.current = true;
    try {
      const [cap, saved] = await Promise.all([
        request<Capabilities>('/capabilities', signal),
        request<{ items: Job[]; total: number }>(`/jobs?operation=image_translate&page=${historyPageRef.current}&page_size=20`, signal),
      ]);
      if (signal.aborted) return;
      setCapabilities(cap);
      if (firstCapabilities.current) {
        firstCapabilities.current = false;
        if (!cap.translation.offline_available && cap.translation.online_available) setOptions(old => ({ ...old, translation_engine: 'online' }));
      }
      setHistory(saved.items); setHistoryTotal(saved.total);
      for (const item of latest.current) {
        if (signal.aborted) return;
        if (item.sourceId && !item.job && ['inspecting', 'awaiting_input'].includes(item.state)) {
          const source = await request<Source>(`/sources/${item.sourceId}`, signal);
          setItems(old => old.map(entry => entry.key === item.key && !entry.job && entry.sourceId === source.id ? {
            ...entry, source, state: source.inspection_status === 'succeeded' ? 'ready' : ['queued', 'running'].includes(source.inspection_status) ? 'inspecting' : source.inspection_status, error: source.error_message,
          } : entry));
        } else if (activeJob(item.job)) {
          const value = await request<Job>(`/jobs/${item.job!.id}`, signal);
          setItems(old => old.map(entry => entry.key === item.key && canApplyJobPoll(entry.job, value)
            ? { ...entry, job: value, state: value.execution_status, error: value.error_message } : entry));
        }
      }
    } catch (err) {
      if (!signal.aborted) setError(message(err));
    } finally { pollBusy.current = false; }
  }
  useEffect(() => {
    const session = new AbortController(); controller.current = session;
    void refresh(session.signal);
    const initialJob = new URLSearchParams(location.search).get('job');
    if (initialJob) void request<Job>(`/jobs/${encodeURIComponent(initialJob)}`, session.signal).then(value => {
      if (!session.signal.aborted && value.operation === 'image_translate') return openJob(value);
    }).catch(err => { if (!session.signal.aborted) setError(message(err)); });
    const timer = window.setInterval(() => void refresh(session.signal), 2500);
    return () => { session.abort(); window.clearInterval(timer); };
  }, []);
  useEffect(() => { void refresh(); }, [historyPage]);
  useEffect(() => { setPage(0); setBox(undefined); setPatching(false); setPassword(''); }, [selected]);
  useEffect(() => { setBox(undefined); setPatching(false); }, [page, view]);

  async function action(work: () => Promise<void>) {
    if (busyLock.current) return;
    busyLock.current = true;
    setBusy(true); setError('');
    try { await work(); } catch (err) { if (!controller.current.signal.aborted) setError(message(err)); }
    finally { busyLock.current = false; if (!controller.current.signal.aborted) setBusy(false); }
  }
  async function addFiles(files: File[]) {
    await action(async () => {
      if (latest.current.length + files.length > 100) throw new Error('每批最多 100 个文件，请分批处理。');
      const signal = controller.current.signal;
      for (const file of files) {
        if (signal.aborted) return;
        if (!/\.(png|jpe?g|webp|pdf)$/i.test(file.name)) throw new Error('支持 PNG、JPEG、WebP 和 PDF 文件。');
        if (file.size > (capabilities?.limits.max_file_bytes ?? 100 * 1024 * 1024)) throw new Error('文件超过服务器上传限制，请拆分后上传。');
        const key = requestId();
        setItems(old => [...old, { key, name: file.name, state: 'uploading' }]);
        setSelected(key); setTab('work');
        const form = new FormData(); form.append('file', file);
        form.append('factory_id', new URLSearchParams(location.search).get('factory') ?? '');
        try {
          const uploaded = await request<{ source_id: string }>('/uploads', signal, form);
          update(key, { sourceId: uploaded.source_id, state: 'inspecting' });
        } catch (err) { update(key, { state: 'failed', error: message(err) }); throw err; }
      }
    });
  }
  useEffect(() => {
    const pasted = (event: ClipboardEvent) => {
      const files = Array.from(event.clipboardData?.files ?? []);
      if (files.length) { event.preventDefault(); void addFiles(files); }
    };
    document.addEventListener('paste', pasted);
    return () => document.removeEventListener('paste', pasted);
  });

  async function create(item: Item) {
    const signal = controller.current.signal;
    const created = await request<{ job_id: string }>('/jobs', signal, { source_id: item.sourceId,
      operation: 'image_translate', options: { ...options, glossary: options.translation_engine === 'online' ? options.glossary : '' }, client_request_id: requestId() });
    const value = await request<Job>(`/jobs/${created.job_id}`, signal);
    update(item.key, { job: value, state: value.execution_status, error: '' });
  }
  async function openJob(value: Job) {
    let item = latest.current.find(entry => entry.job?.id === value.id);
    if (!item) {
      const source = value.source_id ? await request<Source>(`/sources/${value.source_id}`, controller.current.signal) : undefined;
      item = { key: requestId(), name: value.source_name, sourceId: value.source_id, source, job: value, state: value.execution_status };
      setItems(old => [...old, item!]);
    }
    setSelected(item.key); setTab('work');
  }
  async function openCreated(id: string, replaceKey?: string) {
    const value = await request<Job>(`/jobs/${id}`, controller.current.signal);
    if (replaceKey) {
      update(replaceKey, { job: value, state: value.execution_status, error: '' });
      setSelected(replaceKey); setPage(0);
    } else await openJob(value);
  }
  function point(event: PointerEvent) {
    const rect = image.current!.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
  }
  function drag(event: PointerEvent, start: boolean) {
    if (!patching || !image.current || (start && event.button !== 0)) return;
    const p = point(event);
    if (start) { dragStart.current = p; event.currentTarget.setPointerCapture(event.pointerId); }
    const from = dragStart.current;
    if (from) setBox({ x0: Math.min(from.x, p.x), y0: Math.min(from.y, p.y), x1: Math.max(from.x, p.x), y1: Math.max(from.y, p.y) });
  }
  async function submitPatch() {
    if (!job || !box || !results[visiblePage]) return;
    const pageIndex = Number(results[visiblePage].filename.match(/page-(\d+)/)?.[1]) - 1;
    const geometry = current?.source?.manifest.pages?.find(p => p.page_index === pageIndex);
    if (!geometry) throw new Error('页面尺寸不可用，请重新打开任务。');
    const value = await request<{ job_id: string }>(`/jobs/${job.id}/revise`, controller.current.signal, {
      base_revision: job.revision, region: { page_index: pageIndex,
        bbox_pt: [box.x0 * geometry.width_pt, box.y0 * geometry.height_pt, box.x1 * geometry.width_pt, box.y1 * geometry.height_pt] },
    });
    setPatching(false); setBox(undefined); await openCreated(value.job_id, current!.key);
  }

  return <div className="rr-server" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void addFiles(Array.from(event.dataTransfer.files)); }}>
    <header className="rs-header">
      <a className="rs-brand" href={rrToolsUrl()}><img src="/brand/huadeng_group_dynamic_logo_topbar.svg" alt="华登集团" /><span><strong>Royal Regent Nexus</strong><small>公共工具栏</small></span></a>
      <div className="rs-header-actions"><span className="rs-server-tag"><Icon name="shield" />服务器处理</span><a className="rs-back" href={rrToolsUrl()}><Icon name="back" />返回公共工具栏</a></div>
    </header>
    <div className="rs-body">
    <div className="rs-page-heading"><div><span className="rs-eyebrow">公共工具栏</span><h1>图片 / PDF 翻译</h1><p>原位回填译文，保留数字与图稿，逐项对照核对。</p></div>
      <nav className="rs-tabs" aria-label="翻译导航"><button aria-pressed={tab === 'work'} className={tab === 'work' ? 'active' : ''} onClick={() => setTab('work')}><Icon name="image" />工作台</button><button aria-pressed={tab === 'history'} className={tab === 'history' ? 'active' : ''} onClick={() => { setTab('history'); void refresh(); }}><Icon name="clock" />我的历史</button></nav>
    </div>
    {error && <div className="rs-error" role="alert">{error}<button aria-label="关闭提示" onClick={() => setError('')}>×</button></div>}
    {capabilities && !capabilities.worker.online && <div className="rs-notice">后台处理服务暂未就绪，任务会在服务恢复后继续。<button onClick={() => void refresh()}>刷新状态</button></div>}
    <input ref={input} className="visually-hidden" aria-label="添加图片或 PDF" type="file" accept=".png,.jpg,.jpeg,.webp,.pdf" multiple onChange={event => { void addFiles(Array.from(event.target.files ?? [])); event.target.value = ''; }} />
    {tab === 'history' ? <main className="rs-history"><div className="rs-section-title"><h2><Icon name="clock" />我的翻译历史</h2><span>共 {historyTotal} 条 · 仅当前账号可见</span></div>
      {!history.length && <div className="rs-empty"><span className="rs-empty-icon"><Icon name="clock" /></span><h3>暂无翻译记录</h3><p>完成翻译后，可在这里查看和下载结果。</p><button onClick={()=>setTab('work')}>返回工作台</button></div>}
      {history.length > 0 && <div className="rs-history-columns" aria-hidden="true"><span>文件名称</span><span>状态 / 版本</span><span>创建时间</span></div>}
      {history.map(value => <button className="rs-history-row" key={value.id} onClick={() => void action(() => openJob(value))}><strong><Icon name="image" /><span>{value.source_name}</span></strong><span><span className="rs-status" data-state={value.execution_status}>{stateLabel[value.execution_status]}</span><small>第 {value.revision} 版</small></span><time>{new Date(value.created_at).toLocaleString('zh-CN', {hour12:false})}</time></button>)}
      <div className="rs-pagination"><button disabled={historyPage <= 1} onClick={() => setHistoryPage(old => old - 1)}>上一页</button><span>{historyPage} / {Math.max(1, Math.ceil(historyTotal / 20))}</span><button disabled={historyPage * 20 >= historyTotal} onClick={() => setHistoryPage(old => old + 1)}>下一页</button></div>
    </main> : <main className="rs-workspace">
      <aside className="rs-queue"><div className="rs-section-title"><h2><Icon name="queue" />文件队列</h2><span className="rs-count">{items.length} / 100</span></div>
        <button disabled={busy} onClick={() => input.current?.click()}><Icon name="add" />添加图片 / PDF</button>
        <button disabled={busy || !items.some(item => item.job?.artifacts.some(a => a.role === 'result' && a.format === 'pdf'))} onClick={() => void action(async () => {
          const ids = [...new Set(items.flatMap(item => item.job?.artifacts.filter(a => a.role === 'result' && a.format === 'pdf').map(a => a.id) ?? []))];
          const value = await request<{ job_id: string }>('/packages', controller.current.signal, { artifact_ids: ids, format: 'pdf', client_request_id: requestId() });
          await openCreated(value.job_id);
        })}><Icon name="download" />汇总导出 PDF</button>
        <small>按队列顺序汇总已完成的结果。</small>
        <div className="rs-items">{!items.length && <div className="rs-queue-empty"><Icon name="queue" /><p>暂无文件</p><small>支持多选、拖放或粘贴图片</small></div>}{items.map(item => <button key={item.key} aria-pressed={selected === item.key} title={item.name} className={selected === item.key ? 'selected' : ''} onClick={() => setSelected(item.key)}><Icon name="image" /><span className="rs-file-info"><strong>{item.name}</strong><small><span className="rs-status" data-state={item.state}>{stateLabel[item.state] ?? item.state}</span>{item.job && ` · 第 ${item.job.revision} 版`}</small></span></button>)}</div>
      </aside>
      <section className="rs-preview"><div className="rs-preview-toolbar"><div className="rs-document-title"><h2 title={current?.name}>{current?.name ?? '文件预览'}</h2><small>{current ? '对照原图检查文字与排版' : '图片和 PDF 均可添加'}</small></div><div className="rs-view-switch"><button aria-pressed={view === 'source'} className={view === 'source' ? 'active' : ''} onClick={() => setView('source')}>原图</button><button aria-pressed={view === 'result'} className={view === 'result' ? 'active' : ''} onClick={() => setView('result')}>结果</button></div></div>
        <div className="rs-canvas">{shown ? <div style={{width:`${zoom*100}%`}} className={`rs-image-wrap ${patching ? 'patching' : ''}`} onPointerDown={event => drag(event, true)} onPointerMove={event => drag(event, false)} onPointerUp={() => { dragStart.current = undefined; }} onPointerCancel={() => { dragStart.current = undefined; }}>
          <img ref={image} src={artifactUrl(shown)} alt={view === 'source' ? '原图' : '翻译结果'} draggable={false} />
          {highlight && <div className="rs-selection" style={{ left: `${highlight.x0 * 100}%`, top: `${highlight.y0 * 100}%`, width: `${(highlight.x1 - highlight.x0) * 100}%`, height: `${(highlight.y1 - highlight.y0) * 100}%` }} />}
        </div> : sourcePreview && view === 'source' ? sourcePreview.format === 'pdf' ? <iframe title="原 PDF 预览" src={artifactUrl(sourcePreview)} /> : <img className="rs-source-image" src={artifactUrl(sourcePreview)} alt="原图" /> : <div className="rs-empty"><span className="rs-empty-icon"><Icon name={activeJob(job) ? 'clock' : 'image'} /></span><h3>{activeJob(job) ? stageLabel[job!.stage] ?? '处理中' : current ? '文件已就绪' : '添加文件，开始原位翻译'}</h3><p>{activeJob(job) ? '后台正在处理，可稍后在历史中查看结果。' : current ? '选择右侧翻译设置，完成后即可对照原图和译文。' : '将图片或 PDF 拖放到这里，也可以粘贴图片。'}</p>{!current && <><button className="primary" disabled={busy} onClick={()=>input.current?.click()}><Icon name="upload" />选择图片或 PDF</button><small>PNG · JPG · WebP · PDF</small></>}</div>}</div>
        {results.length > 0 && <div className="rs-pagination"><button disabled={visiblePage <= 0} onClick={() => setPage(visiblePage - 1)}>上一页</button><span>{visiblePage + 1} / {results.length}</span><button disabled={visiblePage >= results.length - 1} onClick={() => setPage(visiblePage + 1)}>下一页</button><select aria-label="预览缩放" value={zoom} onChange={event=>setZoom(Number(event.target.value))}><option value={1}>适合宽度</option><option value={1.5}>放大 1.5 倍</option><option value={2}>放大 2 倍</option><option value={3}>放大 3 倍</option></select><a href={artifactUrl(results[visiblePage]!, true)}>下载此页图片</a></div>}
        {job?.execution_status === 'succeeded' && results.length > 0 && <div className="rs-patch"><button aria-pressed={patching} className={patching ? 'active' : ''} disabled={busy} onClick={() => { setPatching(old => !old); setBox(undefined); }}><Icon name="fit" />框选补翻</button>{patching && <><span>在预览图上拖出区域，补翻会生成新版本。</span><button className="primary" disabled={busy || !box || box.x1 === box.x0 || box.y1 === box.y0} onClick={() => void action(submitPatch)}>提交补翻</button></>}</div>}
        {review && <details className="rs-review"><summary>本页逐项核对 · 已回填 {pageRegions.filter(r=>r.rendered).length} 处 · 保留 {pageRegions.filter(r=>!r.rendered).length} 处</summary><div className="rs-review-list">{pageRegions.map(region=><button key={region.id} onClick={()=>{
          const geometry=review.pages.find(p=>p.page_index===region.page_index), b=region.bbox_pt;
          setPatching(false);
          if(geometry&&b) setReviewFocus({x0:b[0]/geometry.width_pt,y0:b[1]/geometry.height_pt,x1:b[2]/geometry.width_pt,y1:b[3]/geometry.height_pt});
        }}><span>{region.source}</span><strong>{region.rendered?region.translation:preserveLabel[region.reason]??'保留待核对'}</strong></button>)}</div></details>}
      </section>
      <aside className="rs-settings"><h2><Icon name="settings" />翻译设置</h2><div className="rs-callout"><strong><Icon name="shield" />无需安装，上传即可处理</strong><p>文件和结果仅当前账号可见。</p></div>
        {current?.source?.manifest.pages?.[0]?.image_resize && <p className="rs-help" role="status">高分辨率图片已自动缩小：{current.source.manifest.pages[0].image_resize.original_size.join(' × ')} → {current.source.manifest.pages[0].image_resize.processing_size.join(' × ')} 像素，原文件保留。</p>}
        <label className="rs-setting-row">翻译方向<select value={options.translation_direction} onChange={event => setOptions(old => ({ ...old, translation_direction: event.target.value as Options['translation_direction'] }))}><option value="en_to_zh">英文 → 简体中文</option><option value="zh_to_en">中文 → 英文</option></select></label>
        <div className="rs-setting-field"><label className="rs-setting-row">翻译方式<select value={options.translation_engine} onChange={event => setOptions(old => ({ ...old, translation_engine: event.target.value as Options['translation_engine'] }))}><option value="offline">服务器离线翻译{capabilities && !capabilities.translation.offline_available ? '（未就绪）' : ''}</option><option value="online">在线 AI 精译{capabilities && !capabilities.translation.online_available ? '（未配置）' : ''}</option></select></label>
          <p className="rs-help">{options.translation_engine === 'offline' ? '服务器本地处理，不外发至 AI。' : '文字与术语发送至配置的 AI 服务。'}</p></div>
        {options.translation_engine === 'online' && <details className="rs-settings-details"><summary>专业术语（可选）</summary><textarea aria-label="专业术语" maxLength={4000} value={options.glossary} onChange={event => setOptions(old => ({ ...old, glossary: event.target.value }))} placeholder="例如：Quantity = 数量" /></details>}
        <div className="rs-setting-field"><label className="rs-setting-row">PDF 页码<input value={options.page_selection} onChange={event => setOptions(old => ({ ...old, page_selection: event.target.value }))} placeholder="all 或 1-3,5" /></label><small>all = 全部页；指定页如 1-3,5。</small></div>
        {capabilities && !capabilities.image_translation?.available && <p role="status" className="rs-error">{capabilities.image_translation?.reason ?? '请联系管理员更新后台图片处理服务。'}</p>}
        <button className="primary rs-start" disabled={busy || !available || !ready.length} onClick={() => void action(async () => { for (const item of ready) await create(item); })}><Icon name="language" />{busy ? '请稍候…' : `开始翻译${ready.length ? `（${ready.length} 个文件）` : ''}`}</button>
        {current?.state === 'awaiting_input' && <form onSubmit={event => { event.preventDefault(); void action(async () => { await request(`/sources/${current.sourceId}/password`, controller.current.signal, { password }); setPassword(''); update(current.key, { state: 'inspecting', error: '' }); }); }}><label>PDF 打开密码<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="off" /></label><button disabled={busy || !password}>解锁文件</button></form>}
        {current?.error && <p className="rs-error" role="alert">{current.error}</p>}
        {job && <section className="rs-task"><h3>当前任务</h3><p><span className="rs-status" data-state={job.execution_status}>{stateLabel[job.execution_status]}</span> · 第 {job.revision} 版</p>{activeJob(job) && <><p>{stageLabel[job.stage] ?? '处理中'}{job.total_units ? ` · ${job.completed_units} / ${job.total_units}` : ''}</p><button disabled={busy} onClick={() => void action(async () => { const value = await request<Job>(`/jobs/${job.id}/cancel`, controller.current.signal, {}); update(current!.key, { job: value, state: value.execution_status }); })}>撤回任务</button></>}
          {['failed', 'cancelled'].includes(job.execution_status) && <button disabled={busy} onClick={() => void action(async () => { const value = await request<{ job_id: string }>(`/jobs/${job.id}/retry`, controller.current.signal, {}); await openCreated(value.job_id, current!.key); })}>重试任务</button>}
          {job.artifacts.filter(a => a.role === 'result' || a.role === 'package').map(artifact => <a className="rs-download" key={artifact.id} href={artifactUrl(artifact, true)}><Icon name="download" /><span>下载 {artifact.filename}</span></a>)}
          {!activeJob(job) && job.source_id && <button disabled={busy || !available} onClick={() => void action(async () => {
            await create(current!);
          })}>按当前设置重新翻译</button>}
          {!activeJob(job) && <button className="rs-danger" disabled={busy} onClick={() => void action(async () => { if (!window.confirm('从任务记录中移除此任务？已保存文件不会被物理删除。')) return; await request(`/jobs/${job.id}`, controller.current.signal, undefined, 'DELETE'); setItems(old => old.filter(item => item.job?.id !== job.id)); setSelected(''); await refresh(); })}><Icon name="trash" />移除任务记录</button>}
        </section>}
        <details className="rs-settings-details"><summary>原文保护说明</summary><p className="rs-help">保留数字、尺寸、型号和色号，只在原文字区域回填。不确定或放不下的内容保留原文，可在“逐项核对”中查看。原文件始终保留；图片整张处理。</p></details>
      </aside>
    </main>}
    </div>
    <footer className="rs-footer">图片处理基于 ShinobuTranslator · <a href="./LICENSE" target="_blank" rel="noreferrer">许可证</a> · <a href="./THIRD_PARTY_NOTICES.md" target="_blank" rel="noreferrer">第三方声明</a></footer>
  </div>;
}
