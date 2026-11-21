/* Printing consumes an explicit, saved snapshot; it never saves workbench drafts. */
(function (root) {
  'use strict';
  const document = root.document;
  const templateName = '客户验货排期表';
  let activeDialog;
  const imageUrl = page => 'data:image/png;base64,' + page.image;

  function pdfUrl(encoded) {
    const binary = root.atob(encoded), bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
    return root.URL.createObjectURL(new Blob([bytes], {type:'application/pdf'}));
  }

  function describe(row) {
    return [row.customer, row.poNo && 'PO ' + row.poNo, row.productNo && '货号 ' + row.productNo, row.productName]
      .filter(Boolean).join(' · ') + (row.testData ? '（测试数据）' : '');
  }

  function open() {
    if (activeDialog && activeDialog.open) { activeDialog.focus(); return; }
    const desk = root.QcInspectionSheet, model = desk && desk.model;
    if (!root.__QC_NEXUS || !root.__QC_NEXUS.exportAllowed) return;
    if (!model || model.view !== 'records' || model.loading || !model.loaded || model.error) {
      root.showToast?.('请先成功读取验货台记录，再生成打印预览。','info');
      return;
    }
    const visible = desk.filtered().slice();
    if (!visible.length) { root.showToast?.('当前筛选没有可打印记录。','info'); return; }
    const dialog = root.QcInspectionAudit.dialog('打印预览', `
      <div class="qip-layout">
        <section class="qip-selection" data-selection aria-label="选择验货记录">
          <div class="qip-record-tools">
            <label class="qip-select-all"><input type="checkbox" data-all>全选</label>
            <select data-date aria-label="按排期日期筛选"><option value="">按日期筛选</option></select>
            <span data-selection-count aria-live="polite"></span>
          </div>
          <div class="qip-records" data-rows></div>
          <button type="button" class="qwf-primary" data-generate>生成预览</button>
        </section>
        <section class="qip-preview" aria-label="真实打印预览">
          <div class="qip-empty" data-empty><strong>选择记录后生成预览</strong><p>按排期表模板排版，确认内容后再打印。</p></div>
          <div data-preview hidden>
            <div class="qip-preview-controls"><strong data-template-name></strong><span data-summary></span></div>
            <div class="qip-page-controls"><button type="button" data-back aria-label="上一页">上一页</button><span data-page-number aria-live="polite"></span><button type="button" data-next aria-label="下一页">下一页</button>
              <label>缩放 <select data-zoom><option value="100">适合宽度</option><option value="125">125%</option><option value="150">150%</option><option value="200">200%</option></select></label>
            </div>
            <div class="qip-paper" tabindex="0" aria-label="打印页预览"><img data-page alt=""></div>
            <details class="qip-selected"><summary data-selected-title></summary><ul data-selected></ul></details>
          </div>
        </section>
      </div>
      <p class="qip-status" data-status role="status" aria-live="polite"></p>
      <footer class="qip-actions">
        <a data-pdf target="_blank" rel="noopener" hidden>打开 PDF</a>
        <button type="button" data-cancel>取消</button>
        <span class="qip-output-actions">
          <button type="button" data-excel disabled>导出 Excel</button>
          <button type="button" class="qwf-primary" data-print disabled>打印</button>
        </span>
      </footer>`);
    activeDialog = dialog;
    dialog.classList.add('qip-dialog');
    const get = name => dialog.querySelector('[data-' + name + ']');
    // Keep actions visible while either the selection list or the paper scrolls.
    dialog.append(get('status'), dialog.querySelector('.qip-actions'));
    const generate = get('generate'), exportExcel = get('excel'), status = get('status');
    const selection = new Set(visible.filter(row => row.id === model.selectedId).map(row => row.id));
    let result, sourcePdf, rasterFrame, currentRequest, requestTimer;
    let currentPage = 0, generation = 0, busy = false, rasterReady = false;
    const dateFilter = get('date'), selectAll = get('all');
    const days = [...new Set(visible.map(row => row.dateFrom || ''))].sort();
    for (const day of days) dateFilter.add(new root.Option(day || '未排期', day || 'undated'));
    let listed = visible;

    function destroyFrames() {
      if (rasterFrame) rasterFrame.remove();
      rasterFrame = undefined; rasterReady = false;
    }
    function invalidate() {
      generation++;
      destroyFrames();
      if (sourcePdf) root.URL.revokeObjectURL(sourcePdf);
      sourcePdf = result = undefined;
      get('pdf').removeAttribute('href'); get('pdf').hidden = true;
      get('page').removeAttribute('src'); get('preview').hidden = true;
      get('empty').hidden = false; get('print').disabled = true;
    }
    function updateSelection() {
      get('selection-count').textContent = '已选 ' + selection.size + ' / ' + listed.length;
      selectAll.checked = listed.length > 0 && selection.size === listed.length;
      selectAll.indeterminate = selection.size > 0 && !selectAll.checked;
      generate.disabled = busy || !selection.size || selection.size > 500;
      exportExcel.disabled = generate.disabled;
      if (selection.size > 500) status.textContent = '一次最多打印 500 条，请缩小筛选范围或分批选择。';
      get('rows').querySelectorAll('input').forEach(input => { input.checked = selection.has(input.value); });
    }
    function changeSelection() { invalidate(); status.textContent = ''; updateSelection(); }
    function card(row) {
      const label = document.createElement('label'), checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.value = row.id; checkbox.checked = selection.has(row.id);
      const text = document.createElement('span'), identity = document.createElement('strong'), detail = document.createElement('small');
      identity.textContent = [row.customer || '未填写客户', row.poNo && 'PO ' + row.poNo].filter(Boolean).join(' · ');
      detail.textContent = [row.productNo, row.productName, row.testData && '测试数据'].filter(Boolean).join(' · ');
      const date = document.createElement('small');
      const dates = [...new Set([row.dateFrom, row.dateTo].filter(Boolean))];
      date.className = 'qip-record-date';
      date.textContent = dates.length ? '排期 ' + dates.join(' 至 ') : '未排期';
      text.append(identity, detail, date); label.append(checkbox, text);
      checkbox.onchange = () => { if (checkbox.checked) selection.add(row.id); else selection.delete(row.id); changeSelection(); };
      return label;
    }
    function renderCards() { get('rows').replaceChildren(...listed.map(card)); get('rows').scrollTop = 0; }
    dateFilter.onchange = () => {
      listed = visible.filter(row => !dateFilter.value || (row.dateFrom || 'undated') === dateFilter.value);
      const ids = new Set(listed.map(row => row.id));
      for (const id of selection) if (!ids.has(id)) selection.delete(id);
      renderCards(); changeSelection();
    };
    selectAll.onchange = () => {
      if (selectAll.checked) listed.forEach(row => selection.add(row.id));
      else selection.clear();
      changeSelection();
    };
    renderCards();
    updateSelection();

    function showPage() {
      if (!result) return;
      currentPage = Math.max(0, Math.min(result.pages.length - 1, currentPage));
      get('page').src = imageUrl(result.pages[currentPage]);
      get('page').alt = '打印预览第 ' + (currentPage + 1) + ' 页';
      get('page-number').textContent = (currentPage + 1) + ' / ' + result.pages.length;
      get('back').disabled = currentPage === 0;
      get('next').disabled = currentPage === result.pages.length - 1;
      dialog.querySelector('.qip-paper').scrollTop = 0;
    }
    function frame(title) {
      const el = document.createElement('iframe'); el.className = 'qip-print-frame'; el.title = title; el.setAttribute('aria-hidden','true');
      el.tabIndex = -1; document.body.append(el); return el;
    }
    function preparePrint() {
      const current = generation;
      // Prepare the final PDF pages before the click handler: native print keeps
      // the user's click activation and never races image decoding.
      rasterFrame = frame('验货台打印内容');
      const output = rasterFrame.contentDocument, style = output.createElement('style'), size = result.pages[0];
      style.textContent = '@page{size:'+size.width+'pt '+size.height+'pt;margin:0}html,body{margin:0;padding:0}.page{width:'+size.width+'pt;height:'+size.height+'pt;overflow:hidden;page-break-after:always}.page:last-child{page-break-after:auto}img{display:block;width:100%;height:100%;object-fit:contain}';
      output.title = '验货台'; output.head.append(style);
      let loaded = 0;
      result.pages.forEach(page => {
        const wrapper = output.createElement('div'), img = output.createElement('img'); wrapper.className = 'page';
        img.onload = () => {
          if (current === generation && result && ++loaded === result.pages.length) { rasterReady = true; get('print').disabled = false; }
        };
        img.onerror = () => { if (current === generation) status.textContent = '打印页加载失败，可重新生成预览，或打开 PDF 打印。'; };
        wrapper.append(img); output.body.append(wrapper); img.src = imageUrl(page);
      });
    }
    async function generateFile(excel) {
      if (busy || !selection.size || selection.size > 500) return;
      const records = desk.filtered().filter(row => selection.has(row.id));
      if (model.loading || model.error || records.length !== selection.size) {
        status.textContent = '所选记录已变化，请关闭预览、刷新验货台后重新选择。'; return;
      }
      if (records.some(row => { const draft = model.drafts.get(row.id); return draft && (draft.dirty || draft.busy || draft.reading || draft.submitting || draft.error || draft.queue?.length); })) {
        status.textContent = '所选记录还有待保存内容。请完成保存后再生成预览。'; return;
      }
      if (!excel) invalidate();
      busy = true;
      exportExcel.disabled = true;
      get('selection').querySelectorAll('input,select,button').forEach(control => { control.disabled = true; });
      status.textContent = excel ? '正在生成排期表…' : '正在按排期表模板生成预览…';
      currentRequest = root.AbortController ? new root.AbortController() : null;
      let timedOut = false;
      requestTimer = root.setTimeout(() => { timedOut = true; if (currentRequest) currentRequest.abort(); }, 150000);
      try {
        const entries = records.map(({id,revision}) => ({id,revision}));
        const response = await root.fetch(excel ? 'api/inspection-sheet/schedule-excel' : 'api/inspection-sheet/print-preview', {
          method:'POST', headers:{'Content-Type':'application/json'}, signal:currentRequest ? currentRequest.signal : undefined,
          body:JSON.stringify(excel ? {entries} : {template:templateName,entries}),
        });
        if (excel && response.ok) {
          const blob = await response.blob();
          if (!dialog.open) return;
          const link = document.createElement('a');
          const url = root.URL.createObjectURL(blob);
          link.href = url; link.download = '客户验货排期表.xlsx';
          document.body.append(link); link.click(); link.remove();
          root.setTimeout(() => root.URL.revokeObjectURL(url), 60000);
          status.textContent = '排期表已生成。';
          return;
        }
        const data = await response.json().catch(() => null);
        if (!dialog.open) return;
        if (!response.ok) throw new Error(data && typeof data.detail === 'string' ? data.detail : '生成文件失败，请重试');
        if (!data || typeof data.pdf !== 'string' || !Array.isArray(data.pages) || !data.pages.length || data.count !== records.length || data.template !== templateName || data.pages.some(page => !page.image || !(page.width > 0) || !(page.height > 0))) throw new Error('打印文件内容不完整，请重试');
        result = data; sourcePdf = pdfUrl(data.pdf); get('pdf').href = sourcePdf; get('pdf').hidden = false;
        get('template-name').textContent = data.template;
        get('summary').textContent = data.count + ' 条记录 · ' + data.pages.length + ' 页';
        get('selected-title').textContent = '本次打印 ' + data.count + ' 条，查看记录明细';
        get('selected').replaceChildren(...records.map(row => { const li = document.createElement('li'); li.textContent = describe(row); return li; }));
        currentPage = 0; get('zoom').value = '100'; get('page').style.width = '100%';
        showPage(); get('preview').hidden = false; get('empty').hidden = true;
        const missing = records.filter(row => !row.dateFrom && !row.dateTo).length;
        status.textContent = missing ? missing + ' 条记录未填写排期日期，模板对应日期保持空白。' : '';
        preparePrint();
      } catch (error) {
        if (dialog.open) {
          if (!excel) invalidate();
          status.textContent = timedOut ? '生成文件超时，请减少记录后重试。' : error.message || '生成文件失败，请重试';
        }
      } finally {
        root.clearTimeout(requestTimer); currentRequest = null; busy = false;
        get('selection').querySelectorAll('input,select,button').forEach(control => { control.disabled = false; }); updateSelection();
      }
    }
    generate.onclick = () => generateFile(false);
    exportExcel.onclick = () => generateFile(true);
    get('back').onclick = () => { currentPage--; showPage(); };
    get('next').onclick = () => { currentPage++; showPage(); };
    get('zoom').onchange = event => { get('page').style.width = event.target.value + '%'; };
    function print() {
      const target = rasterFrame;
      if (!result || !target || !rasterReady) return;
      try {
        target.contentWindow.focus(); target.contentWindow.print();
      } catch (error) { status.textContent = '当前浏览器无法直接调用打印窗口，请打开 PDF 后使用浏览器打印菜单。'; }
    }
    get('print').onclick = print;
    get('cancel').onclick = () => dialog.close();
    dialog.addEventListener('close', () => {
      root.clearTimeout(requestTimer); if (currentRequest) currentRequest.abort(); invalidate(); activeDialog = null;
    }, {once:true});
  }
  const button = document.getElementById('qcInspectionPrint');
  if (button && root.__QC_NEXUS && root.__QC_NEXUS.exportAllowed) {
    button.hidden = false; button.onclick = open;
    if (button.parentElement.classList.contains('qip-toolbar-action')) button.parentElement.hidden = false;
  }
})(window);
