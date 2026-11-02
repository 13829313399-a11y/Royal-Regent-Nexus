/* Nexus owns identity and factory scope; the standalone login is not used here. */
(function () {
  'use strict';
  window.__QC_SYNC_FAILURE = function () {
    window.__QC_BACKEND_OK = false;
    if (document.getElementById('nexusSyncFailure')) return;
    var panel = document.createElement('div');
    panel.id = 'nexusSyncFailure';
    panel.setAttribute('role', 'alert');
    panel.style.cssText = 'position:fixed;inset:0;z-index:999999;background:#fff;color:#17212f;padding:40px;font:16px/1.7 sans-serif';
    var message = document.createElement('p');
    message.textContent = '保存未完成。连接、账号或权限可能已变化，后续写入已暂停。请重新加载后核对服务器记录，不会自动重试未确认的修改。';
    var button = document.createElement('button');
    button.textContent = '重新加载并核对记录';
    button.onclick = function () { window.parent.location.reload(); };
    panel.append(message, button);
    document.body.appendChild(panel);
  };
  // The parent owns factory selection. Never mutate __QC_COMPANY or a local
  // storage key here: changing factory must recreate the authorized frame.
  var factoryBridge = null;
  var factorySwitching = false;
  window.__QC_INITIAL_PAGE = function () {
    var page = factoryBridge?.page;
    return page && document.getElementById('page-' + page) ? page : 'dashboard';
  };
  window.__QC_CURRENT_PAGE = function () { return typeof currentPage === 'string' ? currentPage : 'dashboard'; };
  window.__QC_RENDER_FACTORY_SELECTOR = function () {
    if (!window.__QC_NEXUS || !factoryBridge) return;
    var badge = document.querySelector('#userBadge .user-badge-company');
    if (!badge) return;
    var select = document.createElement('select');
    select.id = 'qcFactorySelect';
    select.className = 'user-badge-company qc-factory-select';
    select.setAttribute('aria-label', 'QC 厂区');
    select.title = '切换厂区，与 Nexus 同步';
    factoryBridge.options.forEach(function (item) {
      var option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.label;
      select.appendChild(option);
    });
    select.value = factoryBridge.factory;
    select.disabled = factorySwitching;
    select.onchange = async function () {
      var selected = select.value;
      select.value = factoryBridge.factory;
      if (factorySwitching || selected === factoryBridge.factory) return;
      factorySwitching = true; select.disabled = true;
      try { await factoryBridge.select(selected); }
      catch (_) { window.showToast?.('厂区切换未完成，请重试', 'error'); }
      finally { factorySwitching = false; select.disabled = false; select.value = factoryBridge.factory; }
    };
    badge.replaceWith(select);
  };
  window.__QC_SET_FACTORY_BRIDGE = function (bridge) {
    if (!window.__QC_NEXUS || bridge.factory !== window.__QC_NEXUS.factory) return;
    factoryBridge = bridge;
    window.__QC_RENDER_FACTORY_SELECTOR();
    // Only carry the page name across factories, never filters, selections or data.
    if (bridge.page && document.getElementById('page-' + bridge.page) && window.showPage
        && window.__QC_CURRENT_PAGE() !== bridge.page) window.showPage(bridge.page);
  };
  window.__QC_CONFIRM_FACTORY_LEAVE = function () {
    var workflow = window.QcWorkflow?.navigationState?.() || {};
    var schedule = window.QcSchedule?.navigationState?.() || {};
    if (workflow.busy || schedule.busy || referenceClearInProgress || window.__QC_PENDING_WRITES > 0) {
      window.alert('正在保存、上传或下载，请完成后再切换厂区。');
      return false;
    }
    if (workflow.dirty || schedule.dirty || document.getElementById('nexusSyncFailure')) {
      return window.confirm('当前厂区有未保存或未确认的内容。切换或离开后将丢弃这些内容，是否继续？');
    }
    return true;
  };
  var referenceClearInProgress = false;
  window.clearQcReferenceData = async function () {
    if (referenceClearInProgress) return;
    if (!can('deleteRecord')) { showToast('当前账号无权限清除参考数据', 'error'); return; }
    var reference = window.__QC_REFERENCE_DATA || { count: 0 };
    if (!reference.count) { showToast('当前没有模板参考数据', 'info'); return; }
    if (!confirm('仅清除未修改的模板参考数据。新录入和修改过的参考记录将保留。确认继续？')) return;
    referenceClearInProgress = true;
    var busy = document.createElement('div');
    busy.setAttribute('role', 'status');
    busy.style.cssText = 'position:fixed;inset:0;z-index:999998;background:#fff;color:#17212f;padding:40px;font:16px/1.7 sans-serif';
    busy.textContent = '正在保存当前修改并清除未修改的参考数据，请稍候…';
    document.body.appendChild(busy);
    try {
      if (!window.__QC_SYNC_NOW || !await window.__QC_SYNC_NOW()) throw new Error('Save not confirmed');
      var response = await fetch('api/reference-data/clear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var result = await response.json();
      alert('已清除 ' + result.deleted + ' 条参考记录；保留 ' + result.protectedCount + ' 条已修改的参考记录。');
      window.location.reload();
    } catch (error) {
      alert('清除结果尚未确认，请重新加载核对服务器记录。');
      window.__QC_SYNC_FAILURE();
    }
  };
  document.addEventListener('DOMContentLoaded', function () {
    if (!window.__QC_NEXUS) { document.body.textContent = '请从 Nexus 的 QC 验货工作台进入。'; return; }
    // A title can be returned safely without building HTML from account data.
    document.title = 'QC 验货工作台';
    var reference = window.__QC_REFERENCE_DATA || { count: 0 };
    var banner = document.getElementById('qcReferenceBanner');
    if (banner && reference.count) {
      banner.hidden = false;
      banner.textContent = '模板参考：' + reference.count + ' 条记录源自东莞兴信原库（含模拟数据），不属于本厂。当前统计和报表包含参考数据；正式使用前可在数据导入页清除未修改的参考记录。';
    }

    var systemMenu = document.getElementById('sysSwitch');
    if (systemMenu) systemMenu.remove();
  });
})();
