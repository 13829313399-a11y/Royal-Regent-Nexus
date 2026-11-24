// Local P0 observer. Pass this function to Chrome DevTools MCP evaluate_script after login.
function installSpatialBaselineProbe() {
  const router = document.getElementById('app')?.__vue_app__?.config.globalProperties.$router
  if (!['127.0.0.1', 'localhost'].includes(location.hostname) || !router) {
    throw new Error('Open the local Vue development build before attaching the probe.')
  }
  window.__rrSpatialP0?.dispose()
  const paths = new Map([
    ['/modules/production', 'portal'],
    ['/modules/production/production-plan', 'standard'],
    ['/modules/production/uv-printing/live', 'uv'],
  ])
  const rows = []
  const events = []
  const tasks = []
  const observers = []
  const rail = new AbortController()
  let batch = ''
  let input = null
  let active = null
  let frame = 0
  const round = value => Math.round(value * 10) / 10
  const observe = (type, list, settings = {}) => {
    if (!PerformanceObserver.supportedEntryTypes.includes(type)) return
    const observer = new PerformanceObserver(records => {
      for (const record of records.getEntries()) {
        list.push({ name: record.name, start: record.startTime, duration: record.duration })
      }
    })
    observer.observe({ type, ...settings })
    observers.push(observer)
  }
  observe('event', events, { durationThreshold: 16 })
  observe('longtask', tasks)
  document.addEventListener('pointerdown', event => {
    if (!batch || !event.isTrusted || location.pathname !== '/modules/production') return
    const card = event.target.closest?.('article[data-route-entry-id]')
    if (!['production-plan', 'uv-printing'].includes(card?.dataset.routeEntryId)) return
    const sample = { start: event.timeStamp, click: null, raf: null,
      destination: card.dataset.routeEntryId === 'uv-printing' ? 'uv' : 'standard',
      mode: document.querySelector('[data-home-motion]')?.dataset.homeMotion }
    input = sample
    requestAnimationFrame(() => { sample.raf = performance.now() - sample.start })
  }, { capture: true, passive: true, signal: rail.signal })
  document.addEventListener('click', event => {
    if (input && event.isTrusted) input.click = event.timeStamp
  }, { capture: true, passive: true, signal: rail.signal })
  const overlays = new MutationObserver(records => {
    if (!active) return
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node instanceof Element && node.matches('.rr-route-motion')) {
          active.attached++
          active.overlayStart = performance.now() - active.commit
        }
      }
      for (const node of record.removedNodes) {
        if (node instanceof Element && node.matches('.rr-route-motion')) {
          active.overlayEnd = performance.now() - active.commit
        }
      }
    }
  })
  overlays.observe(document.body, { childList: true })
  const detach = router.afterEach((to, from, failure) => {
    if (!batch || failure) return
    const source = paths.get(from.path), destination = paths.get(to.path)
    if (!source || !destination || source === destination) return
    const pointer = source === 'portal' && input?.destination === destination ? input : null
    const record = { batch, source, destination, pointer, commit: performance.now(), attached: 0,
      overlayStart: null, overlayEnd: null, frames: [], complete: false, tailOverlays: null, tailAt: null, firstFrameAt: null,
      visible: document.visibilityState, focused: document.hasFocus() }
    rows.push(record)
    input = null
    active = record
    let previous = null
    const tick = time => {
      if (active !== record) return
      if (previous === null) record.firstFrameAt = performance.now() - record.commit
      else record.frames.push(time - previous)
      previous = time
      if (time < record.commit + 450) {
        frame = requestAnimationFrame(tick)
        return
      }
      record.tailAt = performance.now() - record.commit
      record.complete = true
      record.tailOverlays = document.querySelectorAll('.rr-route-motion').length
      active = null
    }
    frame = requestAnimationFrame(tick)
  })
  const result = record => {
    const pointer = record.pointer
    const relevantEvents = pointer ? events.filter(event =>
      (event.name === 'pointerdown' && Math.abs(event.start - pointer.start) < 2) ||
      (event.name === 'click' && pointer.click !== null && Math.abs(event.start - pointer.click) < 2)) : []
    const start = pointer?.start ?? record.commit
    const windowTasks = tasks.filter(task => task.start < record.commit + 450 && task.start + task.duration > start)
    const ms = value => value == null ? null : round(value)
    return { batch: record.batch, from: record.source, to: record.destination, observedMode: pointer?.mode ?? null,
      pointerNextRafMs: ms(pointer?.raf), pointerCommitMs: ms(pointer && (record.commit - pointer.start)),
      eventDurationMs: relevantEvents.length ? round(Math.max(...relevantEvents.map(e => e.duration))) : null,
      overlayAdds: record.attached, overlayStartMs: ms(record.overlayStart), overlayEndMs: ms(record.overlayEnd),
      firstFrameMs: ms(record.firstFrameAt), tailSampleMs: ms(record.tailAt), visible: record.visible, focused: record.focused,
      tailOverlays: record.tailOverlays, complete: record.complete, longTaskMs: windowTasks.map(t => round(t.duration)),
      frameIntervalsMs: record.frames.map(round) }
  }
  window.__rrSpatialP0 = {
    start(name) { batch = name; input = null },
    read() { return rows.map(result) },
    dispose() {
      rail.abort()
      detach()
      overlays.disconnect()
      observers.forEach(observer => observer.disconnect())
      cancelAnimationFrame(frame)
      active = null
      delete window.__rrSpatialP0
    },
  }
  return { eventTiming: PerformanceObserver.supportedEntryTypes.includes('event'),
    longTasks: PerformanceObserver.supportedEntryTypes.includes('longtask'), mode: document.querySelector('[data-home-motion]')?.dataset.homeMotion }
}
