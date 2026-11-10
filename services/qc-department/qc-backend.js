/* 在 QC 初始化前预加载数据，并将业务编辑同步到后端。 */
(function () {
  'use strict';

  var context = window.__QC_NEXUS;
  if (!context?.user?.username || !context.company) return;
  var COMPANY = context.company;
  window.__QC_COMPANY = COMPANY;
  window.__QC_STORAGE_PREFIX = 'nexus_qc_' + context.user.username + '_' + COMPANY + '_';

  var PREFIX = window.__QC_STORAGE_PREFIX;
  var KEY = {
    records:   PREFIX + 'records',

    defectLib: PREFIX + 'defect_library',
    partners:  PREFIX + 'partners',
  };

  /* API 基址：从当前页面路径推导，兼容根部署(/) 与子路径部署(/qc/)。
     根: '' → /api/...   子路径: '/qc' → /qc/api/...（nginx 会剥掉 /qc/ 前缀） */
  var API_BASE = (function () {
    var p = location.pathname.replace(/[^/]*$/, ''); // 取目录部分 '/qc/' 或 '/'
    return p.replace(/\/$/, '');                      // → '/qc' 或 ''
  })();

  window.__QC_BACKEND_OK = false;
  window.__QC_LAST_SYNC = null;
  window.__QC_PENDING_WRITES = 0;
  function trackWrite(promise) {
    window.__QC_PENDING_WRITES++;
    return promise.finally(function () { window.__QC_PENDING_WRITES--; });
  }

  /* 待删除记录 id 队列：app.js 删除记录时标记，下次推送时带给服务端按 id 删除。
     （服务端已改为按 id 合并写入，不再全量替换，删除必须显式告知） */
  window.__QC_PENDING_DELETES = [];
  var deleteRevisions = Object.create(null);
  var nextDeleteRevision = 0;
  var recordPushQueue = Promise.resolve();
  window.__QC_MARK_DELETED = function (ids) {
    if (!Array.isArray(ids)) return;
    for (var i = 0; i < ids.length; i++) {
      var n = Number(ids[i]) || 0;
      if (!n) continue;
      deleteRevisions[n] = ++nextDeleteRevision;
      if (window.__QC_PENDING_DELETES.indexOf(n) === -1) window.__QC_PENDING_DELETES.push(n);
    }
  };

  /* ── 开机：同步 XHR 拉全量（必须同步，才能赶在 app.js 的 init 之前写好 sessionStorage）── */
  function syncBootstrap() {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', API_BASE + '/api/bootstrap?company=' + COMPANY, false); // 同步请求
      xhr.send(null);
      if (xhr.status !== 200) throw new Error('HTTP ' + xhr.status);
      var data = JSON.parse(xhr.responseText);
      window.__QC_TEST_ENTRY_IDS = new Set(data.testEntryIds || []);
      window.__QC_INSPECTION_PLANS = data.inspectionPlans || {};
      window.__QC_KNOWN_RECORD_IDS = new Set((data.records || []).map(function(r) { return r.id; }));
      window.__QC_REFERENCE_DATA = data.referenceData || { count: 0, ids: [] };

      // records → app.js 的 state 形态 { records, nextId }
      sessionStorage.setItem(KEY.records, JSON.stringify({
        records: Array.isArray(data.records) ? data.records : [],
        nextId:  data.nextId || 31,
      }));
      if (Array.isArray(data.defectLib)) sessionStorage.setItem(KEY.defectLib, JSON.stringify(data.defectLib));
      if (Array.isArray(data.partners))  sessionStorage.setItem(KEY.partners,  JSON.stringify(data.partners));

      window.__QC_BACKEND_OK = true;
      console.log('[QC后端] 预加载成功：公司', COMPANY, '记录', (data.records || []).length,
        '不良库', (data.defectLib || []).length);
    } catch (e) {
      window.__QC_BACKEND_OK = false;
      console.warn('[QC后端] 预加载失败：', e.message);
      Object.keys(KEY).forEach(function(k) { sessionStorage.removeItem(KEY[k]); });
    }
  }

  /* ── 写穿透：把本地写入推回后端 ── */
  function post(url, body) {
    if (window.__QC_BACKEND_OK !== true) return Promise.resolve(false); // 后端不可用时不尝试，避免拖慢
    try {
      return trackWrite(fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).then(function (r) {
        window.__QC_LAST_SYNC = { url: url, ok: r.ok, status: r.status, time: new Date().toISOString() };
        if (!r.ok) {
          console.warn('[QC后端] 写回非200:', url, r.status);
          if (window.__QC_SYNC_FAILURE) window.__QC_SYNC_FAILURE();
        }
        return r.ok;
      }).catch(function (err) {
        window.__QC_LAST_SYNC = { url: url, ok: false, error: err && err.message, time: new Date().toISOString() };
        console.warn('[QC后端] 写回失败:', url, err && err.message);
        if (window.__QC_SYNC_FAILURE) window.__QC_SYNC_FAILURE();
        return false;
      }));
    } catch (e) {
      window.__QC_LAST_SYNC = { url: url, ok: false, error: e && e.message, time: new Date().toISOString() };
      console.warn('[QC后端] 写回异常:', url, e && e.message);
      if (window.__QC_SYNC_FAILURE) window.__QC_SYNC_FAILURE();
      return Promise.resolve(false);
    }
  }

  function pushRecords() {
    // Serialize record writes; an earlier replace must finish before a later
    // ordinary save, and only acknowledge deletion revisions actually sent.
    recordPushQueue = recordPushQueue.then(sendRecords, sendRecords);
    return trackWrite(recordPushQueue);
  }
  function sendRecords() {
    try {
      var st = JSON.parse(sessionStorage.getItem(KEY.records) || '{}');
      var deleted = window.__QC_PENDING_DELETES.slice();
      var revisions = deleted.map(function (id) { return deleteRevisions[id]; });
      function acknowledgeDeletes() {
        window.__QC_PENDING_DELETES = window.__QC_PENDING_DELETES.filter(function (id) {
          var index = deleted.indexOf(id);
          return index === -1 || deleteRevisions[id] !== revisions[index];
        });
      }
      /* 整库替换操作（清空数据/恢复示例/替换模式导入）走 replace 通道 */
      var replacement = window.__QC_FORCE_REPLACE;
      if (replacement) {
        return post(API_BASE + '/api/records/replace?company=' + COMPANY, { records: st.records || [] })
          .then(function (ok) { if (ok) { if (window.__QC_FORCE_REPLACE === replacement) window.__QC_FORCE_REPLACE = false; acknowledgeDeletes(); } return ok; });
      }
      return post(API_BASE + '/api/records?company=' + COMPANY, { records: st.records || [], deletedIds: deleted })
        .then(function (ok) { if (ok) acknowledgeDeletes(); return ok; });
    } catch (e) { console.warn('[QC后端] 读本地记录失败', e); }
    return Promise.resolve(false);
  }
  function pushPartners(list) {
    var l = list;
    if (!Array.isArray(l)) { try { l = JSON.parse(sessionStorage.getItem(KEY.partners) || '[]'); } catch (e) { l = []; } }
    return post(API_BASE + '/api/partners?company=' + COMPANY, { partners: l });
  }
  function pushDefects(lib) {
    var l = lib;
    if (!Array.isArray(l)) { try { l = JSON.parse(sessionStorage.getItem(KEY.defectLib) || '[]'); } catch (e) { l = []; } }
    return post(API_BASE + '/api/defects?company=' + COMPANY, { defectLib: l });
  }

  /* ── 劫持 app.js 的三个写入函数（此时 app.js 已解析，函数已挂到 window）── */
  function patchWriters() {
    var patched = false;
    if (typeof window.persist === 'function' && !window.persist.__qcPatched) {
      var origPersist = window.persist;
      window.persist = function () {
        var ret = origPersist.apply(this, arguments);
        pushRecords();
        return ret;
      };
      window.persist.__qcPatched = true;
      patched = true;
    }
    if (typeof window._savePartners === 'function' && !window._savePartners.__qcPatched) {
      var origP = window._savePartners;
      window._savePartners = function (list) {
        var ret = origP.apply(this, arguments);
        pushPartners(list);
        return ret;
      };
      window._savePartners.__qcPatched = true;
      patched = true;
    }
    if (typeof window._saveDefectLib === 'function' && !window._saveDefectLib.__qcPatched) {
      var origDef = window._saveDefectLib;
      window._saveDefectLib = function (lib) {
        var ret = origDef.apply(this, arguments);
        pushDefects(lib);
        return ret;
      };
      window._saveDefectLib.__qcPatched = true;
      patched = true;
    }
    if (patched) console.log('[QC后端] 写入函数已接管');
    return patched;
  }

  function schedulePatchWriters() {
    patchWriters();
    setTimeout(patchWriters, 0);
    setTimeout(patchWriters, 300);
    setTimeout(patchWriters, 1000);
    setTimeout(patchWriters, 2500);
  }

  window.__QC_SYNC_NOW = function () {
    patchWriters();
    return pushRecords();
  };

  /* 本文件早于 app.js 加载：立即预加载，确保 app.js 初始化前 sessionStorage 已是服务器数据 */
  syncBootstrap();

  /* app.js 解析完成后反复接管写入函数，避免线上脚本时序导致只改本地不写服务器 */
  document.addEventListener('DOMContentLoaded', function () {
    schedulePatchWriters();
  });
})();
