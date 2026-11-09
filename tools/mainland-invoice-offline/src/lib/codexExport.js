/** Codex 工作台的导出适配层：只编排现有引擎，计价和版式仍由各厂原引擎负责。 */
import { loadAsset } from './loadAsset.js';
import { HDD_TPLS, generateHddFiles } from './huadeng.js';
import { generateHddLedger, HDD_LEDGER_TPL_FILE } from './hddLedger.js';
import { HXG_CUSTOMERS, HXG_EXTRA_FORMAT, HXG_EXTRA_TPL, HXG_PREPRINTED_TPL, generateHxgFiles } from './huaxing.js';
import { HKA_CUSTOMERS, generateHkaFiles } from './huakangA.js';
import { generateHkbFiles } from './huakangB.js';
import { HKD_CUSTOMERS, HKD_TPLS, generateHkdFiles } from './huakangD.js';
import { BOOKS, parseDetailWorkbook, planSheet, generateOther } from './otherGuests.js';
import { generateDetailMiandan } from './detailMiandan.js';
import { TPL_FILE, parseAnySourceBook, baseOfSheetName, generateMiandan } from './miandan.js';
import { generate } from './engine.js';

const supported = { invoice: new Set(['hdd', 'hxg', 'hka', 'hkb', 'hkd', 'detail', 'zuru']), miandan: new Set(['hdd', 'detail', 'zuru']) };
const safeName = (value) => String(value || '来源').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|\x00-\x1f]/g, '_').trim().slice(0, 80) || '来源';
const textOf = (value) => typeof value === 'string' ? value : value?.text || value?.message || value?.note || '';
const assets = async (pairs) => Object.fromEntries(await Promise.all(pairs.map(async ([key, path]) => [key, await loadAsset(path)])));
const only = (session, records) => ({ ...session.parsed, invoices: records.map((r) => r.raw) });

function detailPlans(session, records) {
  const source = parseDetailWorkbook(session.buffer);
  const groups = new Map();
  for (const record of records) {
    const raw = record.raw;
    if (!raw?.sourceSheet || !raw.generatedRows?.length) throw new Error(`${record.invNo} 缺少出货明细行号，无法精确生成`);
    if (!groups.has(raw.sourceSheet)) groups.set(raw.sourceSheet, []);
    groups.get(raw.sourceSheet).push(raw);
  }
  return [...groups].map(([sheetName, chosen]) => {
    const plan = planSheet(sheetName, source[sheetName]);
    if (!plan) throw new Error(`${sheetName} 没有可用的发票模板`);
    const rowIds = new Set(chosen.flatMap((r) => r.generatedRows));
    const invIds = new Set(chosen.map((r) => String(r.inv)));
    const chunks = plan.chunks.filter((c) => c.lines.some((l) => rowIds.has(l.row)));
    if (chunks.some((c) => c.lines.some((l) => !rowIds.has(l.row)))) throw new Error(`${sheetName} 的选择包含不完整发票，请整票选择`);
    const invoices = plan.invoices.filter((i) => invIds.has(String(i.inv)));
    if (invoices.length !== chosen.length || !chunks.length) throw new Error(`${sheetName} 的选中发票与生成计划不一致，请重新导入`);
    return { ...plan, invoices, chunks };
  });
}

async function invoiceFiles(session, records, { hxgPrintMode = 'auto' } = {}) {
  const parsed = only(session, records), customers = [...new Set(parsed.invoices.map((i) => i.customer))];
  if (session.kind === 'hdd') return generateHddFiles(parsed, await assets(Object.entries(HDD_TPLS).map(([key, conf]) => [key, conf.file])));
  if (session.kind === 'hxg') {
    const paths = new Set(customers.map((c) => HXG_CUSTOMERS[c]?.tplFile));
    paths.add(HXG_PREPRINTED_TPL);
    for (const inv of parsed.invoices) if (inv.extra) paths.add(HXG_EXTRA_TPL[HXG_EXTRA_FORMAT[inv.customer]]);
    if (paths.has(undefined)) throw new Error('华兴所选客户缺少模板配置');
    const templates = await assets([...paths].map((p) => [p, `/hx-tpl/${p}`]));
    // 自动模式由引擎逐客户判断，混合导入也使用各客户对应的打印格式。
    return generateHxgFiles(parsed, templates, { noHead: hxgPrintMode === 'auto' ? 'auto' : hxgPrintMode === 'preprinted' });
  }
  if (session.kind === 'hka') {
    if (customers.some((c) => !HKA_CUSTOMERS[c])) throw new Error('华康A所选客户缺少模板配置');
    return generateHkaFiles(parsed, await assets(customers.map((c) => [c, HKA_CUSTOMERS[c].tpl])));
  }
  if (session.kind === 'hkb') return generateHkbFiles(parsed, await assets([['trade', '/hkb-tpl/华康B贸易.xlsx'], ['intl', '/hkb-tpl/华康B国际.xlsx']]), { splitDn: true });
  if (session.kind === 'hkd') {
    if (customers.some((c) => !HKD_CUSTOMERS[c])) throw new Error('华康D所选客户缺少模板配置');
    const names = [...new Set(customers.map((c) => HKD_CUSTOMERS[c].tpl))];
    return generateHkdFiles(parsed, await assets(names.map((key) => [key, HKD_TPLS[key].file])));
  }
  if (session.kind === 'detail') {
    const plans = detailPlans(session, records);
    const keys = [...new Set(plans.flatMap((p) => p.chunks.map((c) => c.book)))];
    const result = await generateOther({ bookBuffers: await assets(keys.map((key) => [key, BOOKS[key].file])), plans, timestamp: 'codex版' });
    return result.files;
  }
  if (session.kind === 'zuru') {
    if (parsed.invoices.some((i) => i.customer !== 'ZURU')) throw new Error('所选记录含非 ZURU 发票，不能套用 ZURU 模板');
    const tpl = await loadAsset('/zuru-tpl/兴信-zuru.xlsx');
    const result = await generate({ baseBuffer: tpl, baseName: 'codex版', invoices: parsed.invoices,
      selected: new Set(parsed.invoices.map((i) => i.outSheetName)), slimOutput: true, zuruTplBuffer: tpl });
    if (result.skipped.length) throw new Error(`ZURU 生成跳过 ${result.skipped.length} 页，请核对票号`);
    return [{ name: '兴信_ZURU发票_codex版.xlsx', buffer: result.output, notes: [...result.warnings, ...result.report.filter((r) => r.status === 'warn').map((r) => `${r.name}：${r.note}`)] }];
  }
  throw new Error(`未支持的发票类型：${session.kind}`);
}

async function miandanFile(session, records) {
  if (session.kind === 'hdd') {
    const result = await generateHddLedger({ parsed: only(session, records), tplBuffer: await loadAsset(HDD_LEDGER_TPL_FILE) });
    return { name: '华登面单_codex版.xlsx', buffer: result.buffer, invoiceCount: result.invoiceCount, notes: result.warnings };
  }
  const tplBuffer = await loadAsset(TPL_FILE);
  if (session.kind === 'detail') {
    const keys = new Set(records.map((r) => r.raw.key));
    const parsed = { ...session.parsed, groups: session.parsed.groups.map((g) => ({ ...g, rows: g.rows.filter((r) => keys.has(r.key)) })).filter((g) => g.rows.length) };
    const missingDate = records.filter((r) => !r.raw.date);
    if (missingDate.length) throw new Error(`所选 ${missingDate.length} 张票缺日期，无法归入月份面单，请取消选择或补齐原资料`);
    const result = await generateDetailMiandan({ tplBuffer, parsedList: [parsed] });
    return { name: '兴信_其他客面单_codex版.xlsx', buffer: result.buffer, invoiceCount: result.filter.kept, notes: result.warnings };
  }
  const parsed = await parseAnySourceBook(session.buffer, session.name);
  const selectedSheets = new Set(records.map((r) => r.raw.srcSheetName));
  const bases = new Map([...parsed.bases].filter(([, r]) => selectedSheets.has(r.sheetName)));
  const keptBases = new Set([...bases.values()].map((r) => baseOfSheetName(r.sheetName)));
  const missing = records.filter((r) => !keptBases.has(baseOfSheetName(r.raw.srcSheetName)));
  if (missing.length) throw new Error(`面单只使用有日期及合计的末版发票，请选中末版：${missing.slice(0, 5).map((r) => r.sourceSheet || r.raw.srcSheetName).join('、')}`);
  if (!bases.size) throw new Error('所选记录没有可生成面单的末版发票');
  const result = await generateMiandan({ tplBuffer, parsedList: [{ ...parsed, bases }] });
  if (result.sheets.some((s) => s.selfCheck?.fails?.length)) throw new Error('ZURU 面单自检未通过，请核对源文件');
  const notes = [...result.warnings];
  if (bases.size < records.length) notes.push(`面单按末版归并：选中 ${records.length} 页，生成 ${bases.size} 张票的面单记录`);
  return { name: '兴信_ZURU面单_codex版.xlsx', buffer: result.buffer, invoiceCount: bases.size, notes };
}

/** 按来源独立生成，所有选择先校验；不会把不同上传文件的同号票静默合并。 */
export async function generateCodexOutputs(sessions, { selectedRecordIds, outputType = 'invoice', hxgPrintMode = 'auto', onProgress } = {}) {
  if (!supported[outputType]) throw new Error('请选择发票或面单导出');
  if (!['auto', 'preprinted', 'full'].includes(hxgPrintMode)) throw new Error('请选择有效的华兴打印格式');
  const selected = selectedRecordIds == null ? null : new Set(selectedRecordIds);
  const work = sessions.map((s) => ({ session: s, records: (s.records || []).filter((r) => !selected || selected.has(r.id)) })).filter((s) => s.records.length);
  if (!work.length) throw new Error('请至少选择一张发票');
  for (const { session, records } of work) {
    if (!supported[outputType].has(session.kind)) throw new Error(`${session.label || session.name} 暂不支持${outputType === 'miandan' ? '面单' : '发票'}导出，请只选择支持的来源`);
    if (records.some((r) => !r.raw || r.raw.skip)) throw new Error(`${session.name} 含无效或已取消的记录，请重新选择`);
  }
  const files = [], notes = [], used = new Set();
  let invoiceCount = 0;
  for (let index = 0; index < work.length; index++) {
    const { session, records } = work[index];
    onProgress?.({ completed: index, total: work.length, message: `正在生成 ${session.name}` });
    const result = outputType === 'invoice' ? await invoiceFiles(session, records, { hxgPrintMode }) : [await miandanFile(session, records)];
    if (!result.length) throw new Error(`${session.name} 未生成文件，请检查选择与模板配置`);
    if (session.kind === 'hkb' && outputType === 'invoice') {
      // 华康B导入阶段没有独立总额API；取正式生成器末页合计，包含分期/扣款与续页。
      const totals = new Map(result.flatMap((file) => (file.invoices || []).filter((i) => i.ledgerTotal != null).map((i) => [i.pageSrc || i, i.ledgerTotal])));
      for (const record of records) if (totals.has(record.raw)) { record.amount = totals.get(record.raw); record.amountLabel = '已按生成票面核对'; }
    }
    for (const file of result) {
      const base = `${safeName(session.name)}__${file.name || file.fileName}`;
      let name = base, suffix = 1;
      while (used.has(name.toLowerCase())) { suffix++; name = base.replace(/\.xlsx$/i, `_${suffix}.xlsx`); }
      used.add(name.toLowerCase());
      files.push({ ...file, name, sourceId: session.id });
      notes.push(...(file.notes || []).map((n) => `${session.name}：${textOf(n)}`));
    }
    invoiceCount += outputType === 'invoice' ? records.length : result[0].invoiceCount;
    onProgress?.({ completed: index + 1, total: work.length, message: `已生成 ${session.name}` });
  }
  if (work.length > 1) notes.push('多个来源分别生成，文件名保留来源；同号票未自动合并，请依据来源核对后使用。');
  return { files, summary: { invoiceCount, fileCount: files.length }, notes: [...new Set(notes.filter(Boolean))] };
}

const csvCell = (value) => {
  let valueText = value == null ? '' : String(value);
  // 表格软件可将空白/控制字符后的 = + - @ 当作公式，文本单元格统一中和。
  if (/^[\s\x00-\x1f]*[=+\-@]/.test(valueText)) valueText = `'${valueText}`;
  return `"${valueText.replace(/"/g, '""')}"`;
};
const resolutionOf = (resolutions, id) => resolutions instanceof Map ? resolutions.get(id) : resolutions?.[id];
const formatDate = (date) => date instanceof Date ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` : date && typeof date === 'object' && date.y ? `${date.y}-${String(date.m).padStart(2, '0')}-${String(date.d).padStart(2, '0')}` : date || '';

/** 带 BOM 的 CSV，可直接在 Excel/WPS 打开；异常状态仅是核对记录，不改源金额。 */
export function buildCodexAuditCsv(sessions, selectedRecordIds, resolutions = {}) {
  const selected = selectedRecordIds == null ? null : new Set(selectedRecordIds);
  const rows = [['来源文件', '来源标识', '模块', '发票号', '客户', '日期', '币种', '大陆金额', '源工作表', '源行号', '明细行数', '异常/提示', '核对状态', '核对备注', '核对时间']];
  const statusNames = { reviewed: '已核对', deferred: '暂缓处理', open: '待核对' };
  for (const session of sessions) {
    for (const record of session.records || []) {
      if (selected && !selected.has(record.id)) continue;
      const issues = (session.issues || []).filter((issue) => issue.recordId === record.id || issue.recordIds?.includes(record.id) || (!issue.recordId && !issue.recordIds?.length && String(issue.invNo || issue.inv || '') === String(record.invNo)));
      const recordResolution = resolutionOf(resolutions, record.id);
      const entries = issues.length ? issues : [null];
      for (const issue of entries) {
        const resolved = (issue && resolutionOf(resolutions, issue.id)) || recordResolution;
        const status = typeof resolved === 'string' ? resolved : resolved?.status || (issue ? 'open' : '无提示');
        rows.push([session.name, session.id, session.label || session.kind, record.invNo, record.customer, formatDate(record.date), record.currency,
          record.amount ?? record.raw?.ledgerTotal ?? '', record.sourceSheet, (record.sourceRows || []).join('、'), (Array.isArray(record.lines) ? record.lines.length : record.lines) || record.raw?.generatedRows?.length || 0,
          textOf(issue), statusNames[status] || status, resolved?.note || resolved?.comment || '', resolved?.updatedAt || '']);
      }
    }
    // 无法关联具体发票的源文件级提示也保留，避免追溯导出遗失跳过/无法识别说明。
    if (!selected || (session.records || []).some((r) => selected.has(r.id))) {
      for (const issue of session.issues || []) {
        if (issue.recordId || issue.recordIds?.length || ((issue.invNo || issue.inv) && (session.records || []).some((r) => String(r.invNo) === String(issue.invNo || issue.inv)))) continue;
        const resolved = resolutionOf(resolutions, issue.id);
        const status = typeof resolved === 'string' ? resolved : resolved?.status || 'open';
        rows.push([session.name, session.id, session.label || session.kind, issue.invNo || issue.inv || '', '', '', '', '', issue.sheet || '', issue.row || '', '', textOf(issue),
          statusNames[status] || status, resolved?.note || resolved?.comment || '', resolved?.updatedAt || '']);
      }
    }
  }
  return '\uFEFF' + rows.map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
}
