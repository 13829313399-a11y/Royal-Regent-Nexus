// Run with the bundled artifact-tool runtime. Arguments: repository, output directory.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [repo, outputDir] = process.argv.slice(2);
const domain = path.join(repo, 'backend/app/services/injection_scheduling');
const contract = JSON.parse(await fs.readFile(path.join(domain, 'unified_template.json'), 'utf8'));
const wb = Workbook.create();
const sheet = wb.worksheets.add(contract.sheet);
const guide = wb.worksheets.add('填写说明');
const first = contract.first_data_row, last = first + 499;
const letters = (i) => i < 26 ? String.fromCharCode(65 + i) : 'A' + String.fromCharCode(65 + i - 26);
sheet.showGridLines = false;
sheet.tabColor = '#284B63';
sheet.getRange(`A1:AE${last}`).format.font = { name: 'Arial', size: 11, color: '#243746' };
sheet.getRange(`A1:AE${last}`).format.verticalAlignment = 'center';
sheet.getRange(`A1:AE${last}`).format.rowHeight = 23;
sheet.getRange('A2').values = [[contract.version]];
sheet.getRange('A2').format.font = { size: 10, color: '#64748B' };
sheet.getRange('F2').values = [['四厂统一注塑排产计划']];
sheet.getRange('F2').format.font = { size: 16, bold: true };
sheet.getRange('A3').values = [['厂区（必选）']];
sheet.getRange('D3').values = [['排期起点（必填）']];
sheet.getRange('E3').setNumberFormat('yyyy-mm-dd hh:mm');
sheet.getRange('B3').dataValidation = { rule: { type: 'list', values: ['华兴', '华登', '华康 A', '华康 B'] } };
sheet.getRange('B3').format.fill = '#FFF1CC';
sheet.getRange('E3').format.fill = '#FFF1CC';
sheet.getRange('A4').values = [['第 7 行起一行一条需求。蓝字可填，灰底为公式。机号和顺序都留空表示未排机。']];
sheet.getRange('A5').values = [['按表机号与顺序生成待开工计划。具体日期由系统结合班历、换模换色和设备占用计算。']];
sheet.getRange('A4:AE5').format.font = { size: 10, color: '#526477' };
sheet.getRange('A6:AE6').values = [contract.columns.map((column) => column[1])];
sheet.tables.add(`A6:AE${last}`, true, 'InjectionPlanInputs');
sheet.getRange('A6:AE6').format = { fill: '#284B63', font: { color: '#FFFFFF', bold: true }, wrapText: true, horizontalAlignment: 'center', rowHeight: 38 };
const wide = new Set(['mold_code', 'part_name', 'order_no', 'material_raw', 'production_note', 'order_note']);
for (const [i, [key, , kind]] of contract.columns.entries()) {
  const col = letters(i);
  sheet.getRange(`${col}6:${col}${last}`).format.columnWidth = wide.has(key) ? 23 : kind === 'datetime' ? 21 : 15;
  const input = sheet.getRange(`${col}${first}:${col}${last}`);
  input.format.font.color = kind === 'calculated' ? '#243746' : '#225DAD';
  input.format.horizontalAlignment = kind === 'text' ? 'left' : 'right';
  input.setNumberFormat(kind === 'text' ? '@' : kind === 'datetime' ? 'yyyy-mm-dd hh:mm' : '#,##0.####');
  if (kind === 'calculated') input.format.fill = '#EEF2F6';
  if (kind === 'number' || kind === 'integer') {
    input.dataValidation = { rule: { type: kind === 'integer' ? 'whole' : 'decimal', operator: 'greaterThanOrEqual', formula1: 0 } };
  }
}
sheet.getRange('E3').format.columnWidth = 25;
sheet.freezePanes.freezeRows(6);
sheet.freezePanes.freezeColumns(4);
const formulas = {
  K: '=IF(D7="","",IF(COUNT(I7:J7)<2,"",MAX(0,I7-J7)))',
  M: '=IF(OR(COUNT(K7,L7)<2,L7<=0),"",K7/L7*24)',
  U: '=IF(COUNT(K7,R7)<2,"",K7*R7/1000*1.01)',
  V: '=IF(COUNT(K7,T7)<2,"",K7*T7)',
};
for (const [col, formula] of Object.entries(formulas)) {
  sheet.getRange(`${col}7`).formulas = [[formula]];
  sheet.getRange(`${col}7:${col}${last}`).fillDown();
}
sheet.getRange(`A7:A${last}`).conditionalFormats.addCustom('AND($D7<>"",A7="")', { fill: '#FCE5E5', font: { color: '#A61B1B' } });
sheet.getRange(`I7:J${last}`).conditionalFormats.addCustom('AND($D7<>"",I7="")', { fill: '#FFF1CC' });
sheet.getRange(`C7:C${last}`).conditionalFormats.addCustom('AND($B7<>"",OR(C7="",C7<=0))', { fill: '#FCE5E5' });

guide.showGridLines = false;
guide.tabColor = '#94A3B8';
const instructions = [
  ['填写及导入步骤', ''],
  ['1. 确认基础资料', '先在系统当前厂区维护设备和实物模具，公共模具资料由四厂共享。模板不会新建设备或模具。'],
  ['2. 选择厂区和起点', '在计划表 B3 选择厂区，E3 输入固定日期和时间，例如 2026-09-10 08:00。与系统当前厂区一致。'],
  ['3. 填写需求', '第 7 行开始，一行一条需求。需求编号、模号、计划啤数、已啤数必填。没有已啤数填 0。'],
  ['4. 固定需求编号', '例如 HX-202609-001。同一需求一直沿用同一编号，排序也不能改编号。同单拆行使用不同编号。'],
  ['5. 填写已排机任务', '机号逐字参照本厂设备库。机内顺序填正整数 1、2、3……，同一机号不能重复。行顺序可不同。'],
  ['6. 未排机任务', '机号和机内顺序同时留空，导入后进入待排需求。不要填“待排”或“无”作为机号。'],
  ['7. 排产所需资料', '已排机任务须有日目标、机安及可用实物模具。空白工艺参数取公共资料。备注中的暂停、待料、待通知或修模会保留。'],
  ['8. 查看计算列', '灰底列自动计算。欠数 = MAX(0,计划啤数－已啤数)。纯生产小时 = 欠数 ÷ 日目标 × 24。'],
  ['料重和金额', '剩余料重 kg = 欠数 × 每啤净重 g ÷ 1000 × 1.01。剩余加工金额 = 欠数 × 单价/啤。'],
  ['日期和排队', '系统按机号及机内顺序计算具体日期，包含换模换色、班历和实际占用。表外的已有队列保留在前。'],
  ['最早开工时间', '可选。只在该需求不能早于某个时间开工时填写。它是最早允许时间，不是实际开工记录。'],
  ['已啤数口径', '首次导入作为期初累计，不能虚构成系统报工。以后系统发生生产的需求，用标准交换表更新。'],
  ['9. 上传预览', '系统“导入 Excel”选择本文件。只读取计划表。检查原行、机号、顺序和问题提示后应用。'],
  ['10. 导入后检查', '到计划表查看机号，再到看板或甘特检查队列。导入只建立待开工计划，需要实际开工时再操作。'],
  ['发现无效机号或冲突', '系统不静默换机。修正模板或基础资料后重新上传，也可以明确勾选跳过有问题的行。'],
  ['重复导入', '同文件不会重复新增。保留编号可更新尚未在系统独立调整的计划；有并发调整或生产记录时会提示。'],
  ['变更和删除', '表中删行不等于删除系统需求。清空误导入的数据使用系统“更多－清空本厂计划数据”。'],
  ['扩充行数', '预留 500 行。更多需求在表尾扩展并复制灰底公式，每次最多 5000 行。表头第 6 行不要改名或换列。'],
  ['机安和准备工作', '模具机安 A 以公共模具/实际要求为准。自动化、吸盘、夹具是准备参考，不能作为排期硬门槛。'],
  ['字段来源', '按《华兴啤机日排版表9.1.xlsx》的计划表业务字段与计算单位整理，固定为四厂同一版格式。'],
  ['填写示例（不导入）', 'HX-202609-001：机号旧1，顺序1，模号按公共库，计划2400，已啤400，日目标2400，欠数2000。'],
  ['填写示例（不导入）', 'HX-202609-002：机号旧1，顺序2。HX-202609-003：机号及顺序留空，表示尚未安排机台。'],
];
guide.getRange(`A2:B${instructions.length + 1}`).values = instructions;
guide.getRange(`A2:B${instructions.length + 1}`).format = { font: { name: 'Arial', size: 11, color: '#243746' }, rowHeight: 38, verticalAlignment: 'center', wrapText: true };
guide.getRange('A2').format.font = { size: 16, bold: true };
guide.getRange('A2:A24').format.columnWidth = 27;
guide.getRange('B2:B24').format.columnWidth = 100;
guide.getRange('A3:A24').format.font.bold = true;

// Probe representative formula inputs, then restore the empty deliverable.
sheet.getRange('D7').values = [['TEST']];
sheet.getRange('I7:J7').values = [[2400, 400]];
sheet.getRange('L7').values = [[2400]];
sheet.getRange('R7').values = [[10]];
sheet.getRange('T7').values = [[0.25]];
assert.equal(sheet.getRange('K7').values[0][0], 2000);
assert.ok(Math.abs(sheet.getRange('M7').values[0][0] - 20) < 1e-8);
assert.ok(Math.abs(sheet.getRange('U7').values[0][0] - 20.2) < 1e-8);
assert.equal(sheet.getRange('V7').values[0][0], 500);
sheet.getRange('J7').values = [[2500]];
assert.equal(sheet.getRange('K7').values[0][0], 0);
sheet.getRange('J7').clear({ applyTo: 'contents' });
assert.equal(sheet.getRange('K7').values[0][0], '');
sheet.getRange('J7').values = [[0]];
assert.equal(sheet.getRange('K7').values[0][0], 2400);
sheet.getRange('L7').values = [[0]];
assert.equal(sheet.getRange('M7').values[0][0], '');
for (const range of ['D7', 'I7:J7', 'L7', 'R7', 'T7']) sheet.getRange(range).clear({ applyTo: 'contents' });
wb.recalculate();
console.log((await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!', options: { useRegex: true, maxResults: 20 }, maxChars: 1500 })).ndjson);
console.log((await wb.inspect({ kind: 'table', range: '计划表!I7:M9', include: 'values,formulas', tableMaxRows: 3, tableMaxCols: 5, maxChars: 2000 })).ndjson);
await fs.mkdir(outputDir, { recursive: true });
for (const [name, range, file] of [['计划表', 'A1:M12', 'plan-main.png'], ['计划表', 'N6:AE12', 'plan-details.png'], ['填写说明', 'A2:B24', 'instructions.png']]) {
  const preview = await wb.render({ sheetName: name, range, scale: 1.5, format: 'png' });
  await fs.writeFile(path.join(outputDir, file), new Uint8Array(await preview.arrayBuffer()));
}
const file = path.join(outputDir, '四厂统一注塑排产计划模板.xlsx');
await (await SpreadsheetFile.exportXlsx(wb)).save(file);
await fs.mkdir(path.dirname(path.join(domain, 'templates/injection-plan-v1.xlsx')), { recursive: true });
await fs.copyFile(file, path.join(domain, 'templates/injection-plan-v1.xlsx'));
console.log(JSON.stringify({ file, formulaChecks: 'passed', rows: 500 }));
