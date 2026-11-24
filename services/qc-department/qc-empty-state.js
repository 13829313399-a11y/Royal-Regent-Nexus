/* Decorative scene mounted only by the QC views' successful empty-result branches. */
(function () {
  'use strict';

  const script = new URL(document.currentScript.src);
  const titles = {
    schedule: '暂无排期',
    inspection: '暂无验货任务',
    review: '暂无审核记录',
    summary: '暂无验货记录',
    reports: '暂无报告数据',
  };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let motionModule;
  const escape = value => String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  function markup(scene, detail, title = titles[scene]) {
    const description = detail && detail !== title ? '<p>' + escape(detail) + '</p>' : '';
    return '<qc-empty-state scene="' + scene + '"><strong>' + escape(title) +
      '</strong>' + description + '</qc-empty-state>';
  }

  function loadFrame(scene, pose) {
    const image = new Image();
    image.className = 'qc-empty-frame ' + pose;
    image.alt = '';
    image.decoding = 'async';
    image.src = new URL('empty-art/clerk-' + scene + '-' + pose + '.webp', script);
    return image;
  }

  class QcEmptyState extends HTMLElement {
    connectedCallback() {
      const scene = this.getAttribute('scene');
      if (!Object.hasOwn(titles, scene)) return;
      const art = document.createElement('div');
      art.className = 'qc-empty-art';
      art.setAttribute('aria-hidden', 'true');
      const rest = loadFrame(scene, 'rest');
      rest.addEventListener('error', () => art.remove(), {once:true});
      art.append(rest);
      this.prepend(art);
      const tableViewport = this.closest('table')?.parentElement;
      if (tableViewport && this.parentElement.classList.contains('qc-empty-cell')) {
        this.viewportObserver = new ResizeObserver(([entry]) => {
          this.style.maxInlineSize = entry.contentRect.width + 'px';
        });
        this.viewportObserver.observe(tableViewport);
      }
      this.observer = new IntersectionObserver(entries => {
        if (!entries.some(entry => entry.isIntersecting)) return;
        this.observer.disconnect();
        const playback = new AbortController();
        this.playback = playback;
        this.show(scene, art, rest, playback.signal);
      });
      this.observer.observe(this);
    }

    disconnectedCallback() {
      this.observer?.disconnect();
      this.viewportObserver?.disconnect();
      this.playback?.abort();
      this.querySelector('.qc-empty-art')?.remove();
    }

    async show(scene, art, rest, signal) {
      if (reducedMotion.matches || signal.aborted) return;
      try {
        const poses = scene === 'reports' ? ['action', 'middle'] : ['action'];
        const frames = poses.map(pose => loadFrame(scene, pose));
        motionModule ||= import(new URL('qc-empty-motion.js', script)).catch(() => null);
        const [module] = await Promise.all([motionModule, rest.decode(), ...frames.map(image => image.decode())]);
        if (signal.aborted || reducedMotion.matches) return;
        art.append(...frames);
        if (frames.length === 2) art.classList.add('has-middle');

        const canvas = document.createElement('canvas');
        art.append(canvas);
        const renderer = module?.createClerkMotion(canvas, [rest, ...frames], scene);
        let frameId;
        const finish = () => {
          cancelAnimationFrame(frameId);
          art.classList.remove('is-warping');
          canvas.remove();
          renderer?.dispose();
          art.removeEventListener('animationend', finish);
          signal.removeEventListener('abort', finish);
          reducedMotion.removeEventListener('change', stopOnReducedMotion);
        };
        const stopOnReducedMotion = event => {
          if (!event.matches) return;
          art.classList.remove('is-playing');
          finish();
        };
        signal.addEventListener('abort', finish, {once:true});
        reducedMotion.addEventListener('change', stopOnReducedMotion);
        art.addEventListener('animationend', finish, {once:true});
        art.classList.add('is-playing');
        if (!renderer) return;
        const animation = art.getAnimations()[0];
        const draw = () => {
          const progress = Number(getComputedStyle(art).getPropertyValue('--qc-empty-action'));
          art.classList.toggle('is-warping', progress > .001 && progress < .999 && renderer.draw(progress));
          if (animation?.pending || animation?.playState === 'running') frameId = requestAnimationFrame(draw);
        };
        frameId = requestAnimationFrame(draw);
      } catch {
        // The rest pose remains visible if an animation frame cannot be decoded.
      }
    }
  }

  window.QcEmptyState = {markup};
  customElements.define('qc-empty-state', QcEmptyState);
})();
