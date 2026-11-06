// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import * as XLSX from 'xlsx';
import FactoryHdd from '../src/pages/FactoryHdd';
import { generateHddFiles, hddInvoiceTotal } from '../src/lib/huadeng.js';
import { generateHddLedger } from '../src/lib/hddLedger.js';
import { mergeHddInvoiceFiles } from '../src/lib/hddPrintOrder.js';

vi.mock('../src/lib/huadeng.js', async (importOriginal) => ({
  ...await importOriginal(),
  generateHddFiles: vi.fn(),
}));
vi.mock('../src/lib/loadAsset.js', () => ({ loadAsset: vi.fn(async () => new ArrayBuffer(1)) }));
vi.mock('../src/lib/hddLedger.js', () => ({
  HDD_LEDGER_TPL_FILE: '/hdd-ledger-tpl.xlsx',
  generateHddLedger: vi.fn(),
}));
vi.mock('../src/lib/hddPrintOrder.js', () => ({
  mergeHddInvoiceFiles: vi.fn(async () => ({ buffer: new ArrayBuffer(1), renames: [] })),
}));

const excelDate = (month) => (Date.UTC(2026, month - 1, 10) - Date.UTC(1899, 11, 30)) / 86400000;
function sourceFile(name = '华登测试记录.xlsx', crossMonthWarnings = false) {
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
    ['客名:JAKKS PACIFIC (HK) LIMITED', null, null, '(河源华登)(货款)', '华登制品国际有限公司'],
    ['发票日期', '发票NO', '类别', '合约编号', '货号', '数量', '单价', '项目金额', '应收金额'],
    [excelDate(1), '90000', null, 'PO-0', '#ZERO', 0, 0, 0, 0],
    [excelDate(1), '90001', null, 'PO-1', '#A', 100, 2, 200, 200],
    ...(crossMonthWarnings ? [[null, null, null, 'PO-OTHER', '#A-EXTRA', 0, 0, 0, null]] : []),
    [excelDate(2), '90002', null, 'PO-2', '#B', 100, 3, 300, 300],
  ]), 'JAKKS');
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([
    ['客名:Simba Dickie HK Ltd.', null, null, '(河源华登)(货款)', null, '华登制品(香港)有限公司'],
    ['发票日期', '发票NO', '备注', '合约编号', '货号', '数量', '单价', '项目金额', '杂项', '净销售金额'],
    [excelDate(2), '90001', null, 'SC1', 95000001, 100, 10, 1000, null, crossMonthWarnings ? 800 : 950],
  ]), '仙霸');
  const data = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  return { name, arrayBuffer: async () => data };
}

function outputFiles(parsed) {
  const customers = [...new Set(parsed.invoices.map((inv) => inv.customer))];
  return customers.map((customer) => {
    const invoices = parsed.invoices.filter((inv) => inv.customer === customer).flatMap((inv) => {
      const page = { ...inv, pageNo: 0, pageCnt: 1, sheetName: inv.invNo, ledgerTotal: hddInvoiceTotal(inv) };
      // 模拟一张原票拆成两页，以验证金额没有按页重复累计。
      return inv.invNo === '90002' ? [
        { ...page, pageCnt: 2, ledgerTotal: null },
        { ...page, pageNo: 1, pageCnt: 2, sheetName: `${inv.invNo}-1` },
      ] : [page];
    });
    return { label: customer, fileName: `华登_${customer}发票.xlsx`, buffer: new ArrayBuffer(1), sheetCount: invoices.length, invoices };
  });
}

const pick = (file) => fireEvent.change(screen.getByLabelText('记录文件上传'), { target: { files: [file] } });
async function uploadAndParse(file = sourceFile()) {
  pick(file);
  await screen.findByText(file.name);
  fireEvent.click(screen.getByRole('button', { name: '解析预览' }));
  await screen.findByRole('button', { name: '生成发票工作簿（3 张）' });
}
const readBlob = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = reject;
  reader.readAsArrayBuffer(blob);
});

describe('华登 UI 流程验收', () => {
  let downloads;
  beforeEach(() => {
    downloads = [];
    vi.clearAllMocks();
    vi.mocked(generateHddFiles).mockImplementation(async (parsed) => outputFiles(parsed));
    vi.mocked(generateHddLedger).mockImplementation(async ({ parsed }) => ({ buffer: new ArrayBuffer(1), invoiceCount: parsed.invoices.length, sheets: [{ name: '国际' }], warnings: [] }));
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn((blob) => { downloads.push(blob); return 'blob:test'; }) });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('面单按客户和月份筛选整票，筛选变化清除旧下载及未完成结果', async () => {
    render(<FactoryHdd />);
    await uploadAndParse();
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    fireEvent.click(screen.getByRole('button', { name: '生成面单（1 张原票）' }));
    await screen.findByRole('button', { name: '下载华登面单' });
    const sent = vi.mocked(generateHddLedger).mock.calls[0][0].parsed.invoices;
    expect(sent.map(i => i.invNo)).toEqual(['90001']);
    expect(sent.map(i => i.customer)).toEqual(['JAKKS']);
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    expect(screen.queryByRole('button', { name: '下载华登面单' })).toBeNull();
    let finish;
    vi.mocked(generateHddLedger).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    fireEvent.click(screen.getByRole('button', { name: '生成面单（3 张原票）' }));
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    fireEvent.click(screen.getByRole('button', { name: '清空' }));
    await act(async () => finish({ buffer: new ArrayBuffer(1), invoiceCount: 3, sheets: [{ name: '国际' }], warnings: [] }));
    expect(screen.queryByRole('button', { name: '下载华登面单' })).toBeNull();
    expect(screen.getByRole('button', { name: '生成面单（0 张原票）' }).disabled).toBe(true);
  });

  it('仅统计可生成原票，按月份联动票型、金额、重复票提示，清空筛选不能生成', async () => {
    render(<FactoryHdd />);
    await uploadAndParse();
    expect(screen.getByText('发现 1 组重复票号（保留全部记录，请人工确认）：')).toBeTruthy();
    expect(within(screen.getByLabelText('所选发票金额汇总')).getByText('USD 483.50（2 张原票）')).toBeTruthy();
    expect(within(screen.getByLabelText('所选发票金额汇总')).getByText('HKD 918.65（1 张原票）')).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    expect(screen.getByRole('button', { name: '生成发票工作簿（1 张）' }).disabled).toBe(false);
    expect(screen.getByText('USD 193.40（1 张原票）')).toBeTruthy();
    expect(screen.queryByText(/发现 1 组重复票号/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '清空' }));
    expect(screen.getByRole('button', { name: '生成发票工作簿（0 张）' }).disabled).toBe(true);
    expect(generateHddFiles).not.toHaveBeenCalled();
  });

  it('替换为错误文件后清除旧记录和生成区，不能继续生成旧数据', async () => {
    render(<FactoryHdd />);
    await uploadAndParse();
    pick({ name: '不是记录.txt', arrayBuffer: async () => new ArrayBuffer(0) });
    expect(screen.getByText('请上传记录文件（.et / .xls / .xlsx）')).toBeTruthy();
    expect(screen.queryByText('华登测试记录.xlsx')).toBeNull();
    expect(screen.queryByText('2. 生成发票')).toBeNull();
    expect(screen.getByRole('button', { name: '解析预览' }).disabled).toBe(true);
    await uploadAndParse();
    pick({ name: '读取错误.xlsx', arrayBuffer: async () => { throw new Error('读取中断'); } });
    await screen.findByText('读取失败：读取中断');
    expect(screen.getByRole('button', { name: '解析预览' }).disabled).toBe(true);
    expect(screen.queryByText('华登测试记录.xlsx')).toBeNull();
  });

  it('不同客户跨月同号发票的警告分别归属所选月份，不混入未注明月份', async () => {
    render(<FactoryHdd />);
    await uploadAndParse(sourceFile('跨月同号记录.xlsx', true));
    expect(screen.getByText(/其余行还有合约号 PO-OTHER/)).toBeTruthy();
    expect(screen.getByText(/折率 0.8000/)).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    expect(screen.getByText(/其余行还有合约号 PO-OTHER/)).toBeTruthy();
    expect(screen.queryByText(/折率 0.8000/)).toBeNull();
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年1月' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    expect(screen.queryByText(/其余行还有合约号 PO-OTHER/)).toBeNull();
    expect(screen.getByText(/折率 0.8000/)).toBeTruthy();
  });

  it('后上传的文件优先，较慢的旧文件读取不能覆盖新记录', async () => {
    render(<FactoryHdd />);
    let resolveOld;
    pick({ name: '旧记录.xlsx', arrayBuffer: () => new Promise((resolve) => { resolveOld = resolve; }) });
    const current = sourceFile('新记录.xlsx');
    pick(current);
    await screen.findByText('新记录.xlsx');
    await act(async () => resolveOld(await current.arrayBuffer()));
    expect(screen.queryByText('旧记录.xlsx')).toBeNull();
    expect(screen.getByText('新记录.xlsx')).toBeTruthy();
  });

  it('生成只提交所选月份的有效原票，结果支持核对明细与合并下载且续页不重复算金额', async () => {
    render(<FactoryHdd />);
    await uploadAndParse();
    fireEvent.click(screen.getByRole('button', { name: '生成发票工作簿（3 张）' }));
    await screen.findByText('3. 下载发票');
    expect(generateHddFiles.mock.calls[0][0].invoices).toHaveLength(3);
    const totals = screen.getByLabelText('生成发票金额汇总');
    expect(within(totals).getByText('USD 483.50（2 张原票）')).toBeTruthy();
    expect(within(totals).getByText('HKD 918.65（1 张原票）')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '下载核对明细' }));
    const audit = XLSX.read(await readBlob(downloads[0]));
    expect(audit.SheetNames).toEqual(['币种汇总', '发票明细', '问题提示']);
    const summary = XLSX.utils.sheet_to_json(audit.Sheets['币种汇总']);
    expect(summary).toContainEqual({ 币种: 'USD', 源发票数: 2, 票面金额合计: 483.5 });
    const details = XLSX.utils.sheet_to_json(audit.Sheets['发票明细']);
    expect(details).toHaveLength(4);
    expect(details.find((row) => row.工作表 === '90002').整票金额).toBeUndefined();
    expect(details.find((row) => row.工作表 === '90002-1').整票金额).toBe(290.1);
    fireEvent.click(screen.getByRole('button', { name: '勾选合并下载（2 个文件 · 4 页）' }));
    await waitFor(() => expect(mergeHddInvoiceFiles).toHaveBeenCalledOnce());
    const files = mergeHddInvoiceFiles.mock.calls[0][0];
    expect(files.map(file => file.label)).toEqual(['JAKKS', '仙霸']);
    expect(files.flatMap(file => file.invoices).map(inv => [inv.customer, inv.invNo, inv.pageNo])).toEqual([
      ['JAKKS', '90001', 0], ['JAKKS', '90002', 0], ['JAKKS', '90002', 1], ['仙霸', '90001', 0],
    ]);
    expect(screen.getByText(/合并后按客户分组/)).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    expect(screen.queryByText('3. 下载发票')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '生成发票工作簿（1 张）' }));
    await screen.findByText('3. 下载发票');
    expect(generateHddFiles.mock.calls[1][0].invoices.map((inv) => inv.invNo)).toEqual(['90001']);
  });

  it('生成期间更改筛选后，旧任务完成不能显示过期下载结果', async () => {
    render(<FactoryHdd />);
    await uploadAndParse();
    let finish;
    vi.mocked(generateHddFiles).mockImplementationOnce((parsed) => new Promise((resolve) => { finish = () => resolve(outputFiles(parsed)); }));
    fireEvent.click(screen.getByRole('button', { name: '生成发票工作簿（3 张）' }));
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    fireEvent.click(screen.getByRole('checkbox', { name: '2026年2月' }));
    await act(async () => finish());
    expect(screen.queryByText('3. 下载发票')).toBeNull();
    expect(screen.getByRole('button', { name: '生成发票工作簿（1 张）' }).disabled).toBe(false);
  });

  it('核对明细在半分边界消除浮点尾差，正负金额均按票面两位舍入', async () => {
    render(<FactoryHdd />);
    await uploadAndParse();
    vi.mocked(generateHddFiles).mockImplementationOnce(async (parsed) => outputFiles(parsed).map((file) => ({
      ...file,
      invoices: file.invoices.map((inv) => inv.customer === 'JAKKS' && inv.ledgerTotal !== null ? {
        ...inv, ledgerTotal: inv.invNo === '90001' ? 115754.73499999999 : -115754.73499999999,
      } : inv),
    })));
    fireEvent.click(screen.getByRole('button', { name: '生成发票工作簿（3 张）' }));
    await screen.findByText('3. 下载发票');
    fireEvent.click(screen.getByRole('button', { name: '下载核对明细' }));
    const audit = XLSX.read(await readBlob(downloads[0]));
    const details = XLSX.utils.sheet_to_json(audit.Sheets['发票明细']);
    expect(details.find((row) => row.客户 === 'JAKKS' && row.工作表 === '90001').整票金额).toBe(115754.74);
    expect(details.find((row) => row.工作表 === '90002-1').整票金额).toBe(-115754.74);
  });
});
