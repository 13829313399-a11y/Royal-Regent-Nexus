/**
 * 厂区发票记录（出货明细表）预览解析：通用逻辑，不依赖任何客人/模板配置。
 * 用于新厂区对接前期：上传明细表后立即看到 sheet 清单、数据行数、发票号识别情况。
 * 纯 ESM，浏览器 / Node 通用。
 */

import * as XLSX from 'xlsx';

const HEADER_SCAN_ROWS = 8;

/**
 * @returns { sheets: [{ name, dataRows, invCol, invoiceCount, samples }] }
 *   invCol 为找到「发票号」表头的列字母（找不到为 null）；invoiceCount 为该列去重后的票数。
 */
export function parseFactoryWorkbook(arrayBuffer) {
  const wb = XLSX.read(arrayBuffer, { type: 'array', cellDates: true });
  const sheets = [];
  for (const name of wb.SheetNames) {
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, raw: true, defval: null });
    // 前几行找表头：单元格文本含「发票号」
    let headRow = -1, invCol = -1;
    for (let r = 0; r < Math.min(rows.length, HEADER_SCAN_ROWS) && invCol < 0; r++) {
      const row = rows[r] || [];
      for (let c = 0; c < row.length; c++) {
        const v = row[c];
        if (typeof v === 'string' && v.replace(/\s/g, '').includes('发票号')) { headRow = r; invCol = c; break; }
      }
    }
    const dataStart = headRow >= 0 ? headRow + 1 : 1;
    const dataRows = rows.slice(dataStart)
      .filter((r) => (r || []).some((v) => v != null && String(v).trim() !== ''));
    let invoiceCount = null;
    const samples = [];
    if (invCol >= 0) {
      const seen = new Set();
      for (const r of rows.slice(dataStart)) {
        const v = (r || [])[invCol];
        if (v == null || String(v).trim() === '') continue;
        const s = String(v).trim();
        if (!seen.has(s)) { seen.add(s); if (samples.length < 5) samples.push(s); }
      }
      invoiceCount = seen.size;
    }
    sheets.push({
      name, dataRows: dataRows.length,
      invCol: invCol >= 0 ? XLSX.utils.encode_col(invCol) : null,
      invoiceCount, samples,
    });
  }
  return { sheets };
}
