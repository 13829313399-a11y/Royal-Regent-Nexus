/* Non-interactive QC hints for photo annotation and opening the review workbook. */
((root) => {
  'use strict';
  const doc = root.document;
  const prefix = 'qc.guide.photo.';
  const entrance = 460, dwell = 3000, exit = 950;
  const NECK = 10;
  const mounted = new WeakMap();
  let specIdCounter = 0;

  function photoMemory(actor) {
    try {
      return JSON.parse(root.localStorage.getItem(prefix + actor)) || {};
    } catch {
      return {};
    }
  }
  function rememberPhoto(actor, data) {
    try { root.localStorage.setItem(prefix + actor, JSON.stringify(data)); }
    catch { /* A blocked storage setting must not prevent photo work. */ }
  }
  function completePhoto(actor) {
    if (actor) rememberPhoto(actor, {...photoMemory(actor), complete: true});
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function photoCopy(mobile, beside) {
    if (beside) return '<i class="qc-guide-dot is-photo" aria-hidden="true"></i><span>点左侧「箭头 / 圆圈」可标注照片</span>';
    return mobile
      ? '<i class="qc-guide-dot is-photo" aria-hidden="true"></i><span>点上方「箭头 / 圆圈」可标注</span>'
      : '<i class="qc-guide-dot is-photo" aria-hidden="true"></i><span>点上方「箭头 / 圆圈」可标注照片</span>';
  }

  // Smooth C1-continuous balloon path with a rounded curved neck on top.
  function topNeckPath(w, h, nx, neck = NECK) {
    const r = Math.min(15, Math.floor(h / 2));
    const nh = 11;
    const x = clamp(nx, r + nh, Math.max(r + nh, w - r - nh));
    const b = neck + h;
    return [
      `M ${r} ${neck}`,
      `L ${x - nh} ${neck}`,
      `C ${x - 5} ${neck} ${x - 2.6} 1 ${x} 1`,
      `C ${x + 2.6} 1 ${x + 5} ${neck} ${x + nh} ${neck}`,
      `L ${w - r} ${neck}`,
      `A ${r} ${r} 0 0 1 ${w} ${neck + r}`,
      `L ${w} ${b - r}`,
      `A ${r} ${r} 0 0 1 ${w - r} ${b}`,
      `L ${r} ${b}`,
      `A ${r} ${r} 0 0 1 0 ${b - r}`,
      `L 0 ${neck + r}`,
      `A ${r} ${r} 0 0 1 ${r} ${neck}`,
      'Z',
    ].join(' ');
  }

  // Smooth C1-continuous balloon path with a rounded curved neck on the left edge.
  function leftNeckPath(w, h, ny, neck = NECK) {
    const r = Math.min(13, Math.floor(h / 2) - 8);
    const nh = 8;
    const y = clamp(ny, r + nh, Math.max(r + nh, h - r - nh));
    const right = neck + w;
    return [
      `M ${neck + r} 0`,
      `L ${right - r} 0`,
      `A ${r} ${r} 0 0 1 ${right} ${r}`,
      `L ${right} ${h - r}`,
      `A ${r} ${r} 0 0 1 ${right - r} ${h}`,
      `L ${neck + r} ${h}`,
      `A ${r} ${r} 0 0 1 ${neck} ${h - r}`,
      `L ${neck} ${y + nh}`,
      `C ${neck} ${y + 4} 1 ${y + 2.4} 1 ${y}`,
      `C 1 ${y - 2.4} ${neck} ${y - 4} ${neck} ${y - nh}`,
      `L ${neck} ${r}`,
      `A ${r} ${r} 0 0 1 ${neck + r} 0`,
      'Z',
    ].join(' ');
  }

  function applyBalloonGeometry(balloon, {side, bodyW, bodyH, neckPos}) {
    const isLeft = side === 'left';
    const isRight = side === 'right';
    const horizontal = isLeft || isRight;
    const totalW = Math.round(horizontal ? bodyW + NECK : bodyW);
    const totalH = Math.round(horizontal ? bodyH : bodyH + NECK);
    const d = horizontal
      ? leftNeckPath(bodyW, bodyH, neckPos, NECK)
      : topNeckPath(bodyW, bodyH, neckPos, NECK);
    balloon.classList.toggle('is-left-neck', isLeft);
    balloon.classList.toggle('is-right-neck', isRight);
    balloon.classList.toggle('is-top-neck', !horizontal);
    balloon.style.width = `${totalW}px`;
    balloon.style.height = `${totalH}px`;

    const glass = balloon.querySelector('.qc-balloon-glass');
    glass.style.clipPath = `path("${d}")`;
    glass.style.webkitClipPath = `path("${d}")`;

    for (const svg of balloon.querySelectorAll('.qc-balloon-shadow, .qc-balloon-rim')) {
      svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
    }
    for (const p of balloon.querySelectorAll('path[data-balloon-path]')) {
      p.setAttribute('d', d);
    }

    if (horizontal) {
      balloon.style.setProperty('--qc-origin', `${isRight ? totalW : 0}px ${Math.round(neckPos)}px`);
    } else {
      balloon.style.setProperty('--qc-origin', `${Math.round(neckPos)}px 0px`);
    }
  }

  function reviewToolbarGap(controls, host, anchor, width, height) {
    const top = anchor.top + (anchor.height - height) / 2;
    const occupied = [...controls.querySelectorAll('.qis-review-tabs,.qis-review-selects,.qis-review-search,.qis-review-batch-actions')]
      .map(el => el.getBoundingClientRect())
      .filter(rect => rect.width && rect.top < top + height && rect.bottom > top)
      .sort((a, b) => b.right - a.right);
    let right = anchor.left - 8;
    for (const rect of occupied) {
      if (rect.left >= right) continue;
      if (rect.right + width + 8 <= right) break;
      right = rect.left - 8;
    }
    return right - width < host.left + 8 ? null : {left:right - width - host.left, top:top - host.top};
  }

  function followAnchor(host, rootEl, {mode, anchor, controls, mobile, onPlace}) {
    const img = mode === 'photo' ? host.querySelector('img') : null;
    const balloon = rootEl.querySelector('.qc-guide-balloon');
    const copyEl = rootEl.querySelector('.qc-guide-copy');
    let placed = false;
    let lastBeside = null;
    let photoFallback = false;
    let fallbackTimer = null;

    function position() {
      if (!rootEl.isConnected || (mobile && doc.visibilityState === 'hidden')) return;
      const hostRect = host.getBoundingClientRect();
      const anchorRect = anchor.getBoundingClientRect();
      if (!hostRect.width || !anchorRect.width) return;

      if (mode === 'photo') {
        const bodyH = copyEl.offsetHeight || (mobile ? 40 : 42);
        const bodyW0 = Math.ceil(copyEl.offsetWidth || 256);
        const imgRect = img ? img.getBoundingClientRect() : null;
        const hasPhoto = Boolean(imgRect && imgRect.height > 20);
        if (mobile && img && !img.naturalWidth) return;
        if (img && !hasPhoto && !photoFallback && root.ResizeObserver) return;
        const gap = hasPhoto ? imgRect.top - anchorRect.bottom : 999;
        const toolbarRight = anchorRect.right - hostRect.left;
        const toolbarMidY = (anchorRect.top + anchorRect.bottom) / 2 - hostRect.top;
        const canSitBeside = toolbarRight + 6 + NECK + bodyW0 + 10 <= hostRect.width;
        const fitsBelow = gap >= bodyH + NECK + 8;
        const beside = !fitsBelow && canSitBeside;
        // On a narrow phone use the original floating hint below the tools.
        // Its layer ignores touch and does not take space away from the image.
        const noRoom = !mobile && !fitsBelow && !beside;
        rootEl.classList.toggle('qc-guide-no-room', noRoom);
        if (noRoom) return;

        if (beside !== lastBeside) {
          lastBeside = beside;
          copyEl.innerHTML = photoCopy(mobile, beside);
        }
        const bodyW = Math.ceil(copyEl.offsetWidth || bodyW0);

        if (beside) {
          applyBalloonGeometry(balloon, {side: 'left', bodyW, bodyH, neckPos: bodyH / 2});
          balloon.style.left = `${Math.round(toolbarRight + 4)}px`;
          balloon.style.top = `${Math.round(toolbarMidY - bodyH / 2)}px`;
        } else {
          const arrowBtn = anchor.querySelector('[data-mark-tool="arrow"]');
          const circleBtn = anchor.querySelector('[data-mark-tool="circle"]');
          const aRect = arrowBtn?.getBoundingClientRect();
          const cRect = circleBtn?.getBoundingClientRect();
          const targetX = aRect && cRect && aRect.width && cRect.width
            ? (aRect.left + cRect.right) / 2 - hostRect.left
            : (anchorRect.left + anchorRect.right) / 2 - hostRect.left;
          const toolbarBottom = anchorRect.bottom - hostRect.top;
          const toolbarCenterX = (anchorRect.left + anchorRect.right) / 2 - hostRect.left;
          const left = clamp(toolbarCenterX - bodyW / 2, 8, Math.max(8, hostRect.width - bodyW - 8));
          const neckX = clamp(targetX - left, 26, Math.max(26, bodyW - 26));
          applyBalloonGeometry(balloon, {side: 'top', bodyW, bodyH, neckPos: neckX});
          balloon.style.left = `${Math.round(left)}px`;
          balloon.style.top = `${Math.round(toolbarBottom + 4)}px`;
        }
      } else {
        const bodyH = copyEl.offsetHeight || 42;
        const bodyW = Math.ceil(copyEl.offsetWidth || 308);
        const ax = (anchorRect.left + anchorRect.right) / 2 - hostRect.left;
        const ay = anchorRect.bottom - hostRect.top;
        const desiredRight = Math.min(hostRect.width - 4, anchorRect.right - hostRect.left + 8);
        const left = clamp(desiredRight - bodyW, 8, Math.max(8, hostRect.width - bodyW - 8));
        const top = ay + 3;
        const table = host.querySelector('#reviewTableWrap')?.getBoundingClientRect();
        const needsGap = table?.height && hostRect.top + top + bodyH + NECK + 4 > table.top;
        const gap = needsGap ? reviewToolbarGap(controls, hostRect, anchorRect, bodyW + NECK, bodyH) : null;
        const neckPos = gap ? bodyH / 2 : clamp(ax - left, 26, Math.max(26, bodyW - 26));
        applyBalloonGeometry(balloon, {side: gap ? 'right' : 'top', bodyW, bodyH, neckPos});
        balloon.style.left = `${Math.round(gap?.left ?? left)}px`;
        balloon.style.top = `${Math.round(gap?.top ?? top)}px`;
      }

      if (!placed) {
        placed = true;
        root.clearTimeout(fallbackTimer);
        onPlace?.();
      }
    }

    const schedulePosition = () => {
      if (root.requestAnimationFrame) root.requestAnimationFrame(() => root.requestAnimationFrame(position));
      else position();
    };
    if (mode === 'photo' && img && root.ResizeObserver) {
      fallbackTimer = root.setTimeout(() => { photoFallback = true; position(); }, 180);
    }
    position();
    schedulePosition();
    img?.addEventListener('load', schedulePosition);
    if (mobile) doc.addEventListener('visibilitychange', schedulePosition);
    const observer = root.ResizeObserver ? new root.ResizeObserver(position) : null;
    observer?.observe(host);
    observer?.observe(anchor);
    if (controls && controls !== anchor) observer?.observe(controls);
    if (img) observer?.observe(img);
    observer?.observe(copyEl);
    return () => {
      root.clearTimeout(fallbackTimer);
      observer?.disconnect();
      img?.removeEventListener('load', schedulePosition);
      if (mobile) doc.removeEventListener('visibilitychange', schedulePosition);
    };
  }

  function pulseOrigins(targets) {
    const active = targets.filter(Boolean);
    for (const el of active) {
      el.classList.remove('qc-guide-origin-pulse');
      void el.offsetWidth;
      el.classList.add('qc-guide-origin-pulse');
    }
    return () => {
      for (const el of active) el.classList.remove('qc-guide-origin-pulse');
    };
  }

  function mount(host, {mode, copy, anchor, controls, mobile = false, name, pulse = [], onShown}) {
    mounted.get(host)?.destroy();
    const uid = ++specIdCounter;
    const specId = `qc-balloon-spec-${uid}`;
    const shadowId = `qc-balloon-shadow-${uid}`;
    const bar = doc.createElement('div');
    const hasPendingPhoto = mode === 'photo' && Boolean(host.querySelector('img'));
    const awaitLayout = Boolean(root.ResizeObserver && (!host.getBoundingClientRect().width || hasPendingPhoto));
    bar.className = `qc-glass-guide qc-guide-${mode} ${awaitLayout ? 'qc-guide-await' : 'qc-guide-enter'}`;
    bar.setAttribute('role', 'status');
    bar.setAttribute('aria-live', 'polite');
    bar.setAttribute('aria-label', name);
    bar.innerHTML =
      `<div class="qc-guide-balloon is-top-neck">` +
        `<svg class="qc-balloon-shadow" aria-hidden="true">` +
          `<defs><filter id="${shadowId}" x="-20%" y="-40%" width="140%" height="220%" color-interpolation-filters="sRGB">` +
            `<feOffset dy="9" in="SourceAlpha" result="off1"/>` +
            `<feGaussianBlur stdDeviation="10" in="off1" result="blur1"/>` +
            `<feComponentTransfer in="blur1" result="s1"><feFuncA type="linear" slope="0.16"/></feComponentTransfer>` +
            `<feOffset dy="2" in="SourceAlpha" result="off2"/>` +
            `<feGaussianBlur stdDeviation="2.5" in="off2" result="blur2"/>` +
            `<feComponentTransfer in="blur2" result="s2"><feFuncA type="linear" slope="0.09"/></feComponentTransfer>` +
            `<feMerge result="shadows"><feMergeNode in="s1"/><feMergeNode in="s2"/></feMerge>` +
            `<feComposite operator="out" in="shadows" in2="SourceAlpha"/>` +
          `</filter></defs>` +
          `<path filter="url(#${shadowId})" data-balloon-path></path>` +
        `</svg>` +
        `<div class="qc-balloon-glass" aria-hidden="true"></div>` +
        `<svg class="qc-balloon-rim" aria-hidden="true">` +
          `<defs><linearGradient id="${specId}" x1="0" y1="0" x2="0" y2="1">` +
            `<stop offset="0%" stop-color="#ffffff" stop-opacity="0.96"/>` +
            `<stop offset="45%" stop-color="#ffffff" stop-opacity="0.34"/>` +
            `<stop offset="100%" stop-color="#ffffff" stop-opacity="0.06"/>` +
          `</linearGradient></defs>` +
          `<path class="qc-rim-spec" stroke="url(#${specId})" data-balloon-path></path>` +
          `<path class="qc-rim-outer" data-balloon-path></path>` +
        `</svg>` +
        `<div class="qc-guide-copy">${copy}</div>` +
      `</div>`;
    host.append(bar);

    let timer = null, pulseTimer = null, closing = false, started = false;
    let clearPulse = null;

    function startLifecycle() {
      if (started || closing || !bar.isConnected) return;
      started = true;
      onShown?.();
      bar.classList.remove('qc-guide-await');
      bar.classList.add('qc-guide-enter');
      clearPulse = pulseOrigins(pulse);
      pulseTimer = root.setTimeout(() => clearPulse?.(), 1400);
      timer = root.setTimeout(() => {
        if (closing || !bar.isConnected) return;
        bar.classList.remove('qc-guide-enter');
        timer = root.setTimeout(fade, dwell);
      }, entrance);
    }

    const stopFollow = followAnchor(host, bar, {mode, anchor, controls, mobile, onPlace: startLifecycle});
    if (!root.ResizeObserver && !mobile) startLifecycle();

    function destroy() {
      root.clearTimeout(timer);
      root.clearTimeout(pulseTimer);
      timer = null;
      pulseTimer = null;
      clearPulse?.();
      stopFollow?.();
      bar.remove();
      if (mounted.get(host) === controller) mounted.delete(host);
    }
    function fade() {
      if (closing) return;
      closing = true;
      root.clearTimeout(timer);
      bar.classList.remove('qc-guide-await', 'qc-guide-enter');
      bar.classList.add('qc-guide-out');
      timer = root.setTimeout(destroy, exit);
    }

    const controller = {fade, destroy};
    mounted.set(host, controller);
    return controller;
  }

  function photo(toolbar, {actor, mobile = false} = {}) {
    if (!actor || !toolbar?.parentElement) return null;
    const memory = photoMemory(actor);
    if (!mobile && (memory.complete || (memory.count || 0) >= 2)) return null;
    const pulse = [
      toolbar.querySelector('[data-mark-tool="arrow"]'),
      toolbar.querySelector('[data-mark-tool="circle"]'),
    ];
    return mount(toolbar.parentElement, {
      mode: 'photo',
      name: '照片标注提示',
      anchor: toolbar,
      mobile,
      pulse,
      onShown: mobile ? undefined : () => rememberPhoto(actor, {count: (memory.count || 0) + 1}),
      copy: photoCopy(mobile, false),
    });
  }

  function review(controls, {anchor, unread, read} = {}) {
    const host = controls?.closest?.('.qis-review-surface') || controls?.parentElement;
    if (!host || !anchor) return null;
    const copy =
      `<i class="qc-guide-dot" aria-hidden="true"></i><span>新上传 <b>${unread}</b> 条</span>` +
      `<span class="qc-guide-sep" aria-hidden="true">·</span>` +
      `<i class="qc-guide-dot is-read" aria-hidden="true"></i><span>已读 <b>${read}</b> 条</span>` +
      `<span class="qc-guide-sep qc-guide-review-extra" aria-hidden="true">·</span>` +
      `<span class="qc-guide-review-extra">点展开核对</span>`;
    return mount(host, {
      mode: 'review',
      name: '展开核对提示',
      anchor,
      controls,
      pulse: [anchor],
      copy,
    });
  }

  root.QcGlassGuide = {photo, completePhoto, review};
})(window);
