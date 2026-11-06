/* ══════════════════════════════════════════════════════════════
   兴信 QMS · 移动端交互 + 检测  mobile.js
   ────────────────────────────────────────────────────────────
   1) 检测是否手机/平板 → 给 <html> 加 .qc-mobile / .qc-narrow
      （触发 mobile.css）。判断综合「触摸能力 + 物理屏幕短边 + matchMedia」，
      不依赖 viewport 宽度，规避「电脑版网站」模式伪装宽屏导致 @media 失效。
   2) 手机端侧边栏「抽屉」开合（默认收起、点导航/遮罩关闭），不改 app.js。
══════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var html = document.documentElement;

  /* ── 1. 设备检测 → 打类 ── */
  function isTouch() {
    return (navigator.maxTouchPoints > 0) || ('ontouchstart' in window) ||
      (window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  }
  function shortSide() {
    var w = (window.screen && window.screen.width) || 9999;
    var h = (window.screen && window.screen.height) || 9999;
    return Math.min(w, h);
  }
  function mq(q) { return window.matchMedia && window.matchMedia(q).matches; }

  function evalClasses() {
    var touch = isTouch();
    var ss = shortSide();
    // 手机/平板：媒体查询命中(普通移动浏览器) 或 触摸且物理短边<=820(桌面模式兜底)
    var isPhone  = mq('(max-width: 768px)') || (touch && ss <= 820);
    // 窄屏：媒体查询<=480 或 触摸且物理短边<=480(绝大多数手机)
    var isNarrow = mq('(max-width: 480px)') || (touch && ss <= 480);
    html.classList.toggle('qc-mobile', !!isPhone);
    html.classList.toggle('qc-narrow', !!isNarrow);
    return !!isPhone;
  }

  // 尽早打类，减少布局闪烁（mobile.js 在 body 末尾，<html> 已存在）
  evalClasses();

  /* ── 2. 侧边栏抽屉 ── */
  var sidebar, mainWrap, backdrop;

  function isMobileNow() { return html.classList.contains('qc-mobile'); }

  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.add('collapsed');
    document.body.classList.remove('qc-sidebar-open');
  }
  function syncBackdrop() {
    if (!sidebar) return;
    if (!sidebar.classList.contains('collapsed') && isMobileNow()) {
      document.body.classList.add('qc-sidebar-open');
    } else {
      document.body.classList.remove('qc-sidebar-open');
    }
  }

  // Mobile shortcuts operate on the existing table and controls, never a second draft.
  function initInspectionTools() {
    if (!window.__QC_NEXUS) return;
    var topbar = document.querySelector('.topbar');
    var tools = topbar && topbar.querySelector('.topbar-right');
    if (tools) {
      tools.id = 'qcMobileHeaderTools';
      var headerToggle = document.createElement('button');
      headerToggle.type = 'button';
      headerToggle.className = 'qis-mobile-header-toggle';
      headerToggle.textContent = '工具';
      headerToggle.setAttribute('aria-controls', tools.id);
      headerToggle.setAttribute('aria-expanded', 'false');
      headerToggle.onclick = function () {
        var open = topbar.classList.toggle('qis-tools-open');
        headerToggle.setAttribute('aria-expanded', String(open));
      };
      topbar.appendChild(headerToggle);
    }
    ['records', 'review'].forEach(function (view) {
      var page = document.getElementById('page-' + view);
      var host = document.getElementById(view === 'records' ? 'recordsTableWrap' : 'reviewTableWrap');
      if (!page || !host) return;
      var bar = document.createElement('nav');
      bar.className = 'qis-mobile-tools';
      bar.setAttribute('aria-label', '验货表格快捷定位');
      if (view === 'records') {
        var toolbar = page.querySelector('.records-toolbar');
        toolbar.id = 'qisRecordsToolbar';
        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.textContent = '更多筛选 / 操作';
        toggle.setAttribute('aria-controls', toolbar.id);
        toggle.setAttribute('aria-expanded', 'false');
        toggle.onclick = function () {
          var open = page.classList.toggle('qis-tools-open');
          toggle.setAttribute('aria-expanded', String(open));
          toggle.textContent = open ? '收起筛选 / 操作' : '更多筛选 / 操作';
        };
        bar.appendChild(toggle);
      }
      [['订单', 'date'], ['填写', 'result'], ['照片', 'photos']].forEach(function (item) {
        var button = document.createElement('button');
        button.type = 'button';
        button.textContent = item[0];
        button.setAttribute('aria-controls', host.id);
        button.onclick = function () {
          var target = host.querySelector('th[data-column="' + item[1] + '"]');
          if (!target) return;
          var frozen = Number.parseFloat(host.style.getPropertyValue('--qis-frozen-width')) || 0;
          host.scrollLeft = item[1] === 'date' ? 0 : Math.max(0,
            host.scrollLeft + target.getBoundingClientRect().left - host.getBoundingClientRect().left - host.clientLeft - frozen);
        };
        bar.appendChild(button);
      });
      host.before(bar);
    });
  }

  function init() {
    initInspectionTools();
    sidebar = document.getElementById('sidebar');
    mainWrap = document.querySelector('.main-wrap');
    if (!sidebar) return;

    backdrop = document.createElement('div');
    backdrop.className = 'qc-mobile-backdrop';
    backdrop.addEventListener('click', closeSidebar);
    document.body.appendChild(backdrop);

    if (isMobileNow()) closeSidebar();

    var navItems = sidebar.querySelectorAll('.nav-item');
    for (var i = 0; i < navItems.length; i++) {
      navItems[i].addEventListener('click', function () {
        if (isMobileNow()) closeSidebar();
      });
    }

    // ☰ 用 app.js 的 toggleSidebar()（切 .collapsed）；观察 class 变化同步遮罩
    var mo = new MutationObserver(syncBackdrop);
    mo.observe(sidebar, { attributes: true, attributeFilter: ['class'] });

    // 屏幕尺寸/方向变化时重算
    function onResize() {
      var phone = evalClasses();
      if (phone) { closeSidebar(); }
      else {
        // 桌面端：尊重用户记忆（localStorage），不强制展开；默认隐藏
        var collapsed = true;
        try {
          var v = localStorage.getItem('xingxin_qms_sidebar_collapsed');
          if (v !== null) collapsed = v === '1';
        } catch (e) {}
        sidebar.classList.toggle('collapsed', collapsed);
        if (mainWrap) mainWrap.classList.toggle('full', collapsed);
        document.body.classList.remove('qc-sidebar-open');
      }
    }
    window.addEventListener('resize', onResize);
    window.addEventListener('orientationchange', onResize);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
