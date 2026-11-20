// Bundled artifact-tool runtime only. Args: layout JSON, output folder, template spec JSON.
import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";
import assert from "node:assert/strict";
const [layoutPath, outputDir, specPath] = process.argv.slice(2);
const layout = JSON.parse(await fs.readFile(layoutPath, "utf8"));
const spec = JSON.parse(await fs.readFile(specPath, "utf8"));
const col = (n) => {
  let s = "";
  for (; n; n = Math.floor((n - 1) / 26))
    s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
  return s;
};
const wb = Workbook.create(),
  sh = wb.worksheets.add("计划表");
await fs.mkdir(outputDir, { recursive: true });
const nativeStyle = (style) => {
  const a = style.alignment;
  return {
    font: style.font,
    ...(style.fill ? { fill: style.fill } : {}),
    numberFormat: style.numberFormat,
    ...(a.horizontal ? { horizontalAlignment: a.horizontal } : {}),
    verticalAlignment: "center",
    wrapText: a.wrapText === "1",
  };
};
// First render a source-only view, preserving the original visible column order.
sh.getRange("A1:BB25").format.font = { name: "宋体", size: 9 };
for (const dim of layout.columns)
  for (let i = +dim.min; i <= Math.min(+dim.max, 52); i++) {
    sh.getRange(`${col(i)}1:${col(i)}25`).format.columnWidth = dim.hidden
      ? 0
      : +dim.width;
  }
for (const [r, row] of Object.entries(layout.rows)) {
  if (+r > 25) continue;
  sh.getRange(`A${r}:BB${r}`).format.rowHeight = row.height;
  for (const [c, cell] of Object.entries(row.cells)) {
    sh.getRange(`${c}${r}`).format = nativeStyle(layout.styles[cell.style]);
    if (cell.cached_value !== undefined)
      sh.getRange(`${c}${r}`).values = [[cell.cached_value]];
  }
}
sh.mergeCells("A1:AX1");
await fs.writeFile(
  `${outputDir}/source-view.png`,
  new Uint8Array(
    await (
      await wb.render({ sheetName: "计划表", range: "A1:AX20", scale: 1.5 })
    ).arrayBuffer(),
  ),
);
if (process.env.REFERENCE_ONLY === "1") process.exit(0);
sh.getRange("A1:BB30").clear({ applyTo: "all" });
sh.unmergeCells("A1:AX1");
const last = spec.lastRow,
  pending = spec.pendingRow;
sh.getRange(`A1:DJ${last}`).format = {
  font: { name: "宋体", size: 9, color: "#000000" },
  rowHeight: 18,
  verticalAlignment: "center",
};
for (const dim of layout.columns)
  for (let i = +dim.min; i <= Math.min(+dim.max, 52); i++) {
    sh.getRange(`${col(i)}1:${col(i)}${last}`).format.columnWidth = dim.hidden
      ? 0
      : +dim.width;
  }
// Native hidden flags are restored by the application's XLSX metadata writer.
// Original narrow quantity columns show #### even for ordinary four-digit orders.
for (const column of ["K", "L", "M", "N", "O"])
  sh.getRange(`${column}1:${column}${last}`).format.columnWidth = 11;
sh.getRange(`I1:I${last}`).format.columnWidth = 17;
sh.getRange("DZ1:EU4").format.columnWidth = 0;
sh.getRange("EN3:EU3").values = [
  ["本厂机号", "查找键", "规格", "机型", "机械手", "车间", "状态", "设备备注"],
];
sh.getRange("A1:AX1").merge();
sh.getRange("A1").values = [["厂区啤机排产日计划表"]];
sh.getRange("A1:AX1").format = nativeStyle(
  layout.styles[layout.rows["1"].cells.A.style],
);
sh.getRange("A1:AX1").format.rowHeight = 25;
sh.getRange("A3:AX3").values = [layout.headers];
for (const [c, cell] of Object.entries(layout.rows["3"].cells)) {
  if (c.length === 1 || c <= "AX")
    sh.getRange(`${c}3`).format = nativeStyle(layout.styles[cell.style]);
}
sh.getRange("A3:DJ3").format.rowHeight = 42;
sh.getRange("A3:DJ3").format.wrapText = true;
sh.getRange("E2").values = [["厂区"]];
sh.getRange("F2").dataValidation = {
  rule: { type: "list", values: ["华兴", "华登", "华康 A", "华康 B"] },
};
sh.getRange("F2").format.fill = "#FFF2CC";
sh.getRange("G2").values = [["剩余啤货数"]];
sh.getRange("H2").formulas = [[`=SUM(N4:N${last})`]];
sh.getRange("H2").setNumberFormat("#,##0");
sh.getRange("I2:K2").merge();
sh.getRange("I2").setNumberFormat("yyyy-mm-dd hh:mm");
sh.getRange("I2:K2").format.fill = "#FFF2CC";
sh.getRange("L2:O2").merge();
sh.getRange("L2").values = [["排期起点填左侧黄格"]];
sh.getRange("Q2:S2").merge();
sh.getRange("Q2").values = [["机台下方从上到下排队"]];
sh.getRange("AR2:AS2").merge();
sh.getRange("AR2").values = [["模具参数随下载更新"]];
sh.getRange("AW2:AX2").merge();
sh.getRange("AW2").values = [["期初已啤"]];
sh.getRange("AW2:AX2").format.font.size = 9;
sh.getRange("AY1").values = [[spec.version]];
sh.getRange("AY2").values = [["统一厂区计划"]];
sh.getRange("EM1").values = [[3]];
sh.getRange("EM2").values = [[0.01]];
sh.getRange("DZ3:EL3").values = [
  [
    "模号",
    "名称",
    "机型",
    "日目标",
    "净重",
    "毛重",
    "单价",
    "机械手",
    "夹具",
    "自动化",
    "转模天数",
    "转色天数",
    "机安A",
  ],
];
for (let d = 0; d < 31; d++) {
  const a = col(53 + d * 2),
    b = col(54 + d * 2);
  sh.getRange(`${a}2:${b}2`).merge();
  sh.getRange(`${a}2`).formulas = [[`=IF(COUNT($I$2)=0,"",INT($I$2)+${d})`]];
  sh.getRange(`${a}2:${b}2`).setNumberFormat("m/d");
  sh.getRange(`${a}3:${b}3`).values = [["白班", "夜班"]];
  sh.getRange(`${a}1:${b}${last}`).format.columnWidth = 6;
  sh.getRange(`${a}2:${b}3`).format = {
    fill: "#D9EAD3",
    horizontalAlignment: "center",
    font: { size: 9 },
  };
}
const lookup = (r, index, numeric = false) => {
  // A one-row prototype keeps artifact calculation bounded. Download expands only
  // these exact absolute lookup ranges to the actual master snapshot size.
  const value = `VLOOKUP($G${r},$DZ$4:$EL$4,${index},FALSE)`;
  const input = col(129 + index);
  const present = `COUNTIFS($DZ$4:$DZ$4,$G${r},$${input}$4:$${input}$4,"<>")`;
  return `=IF($G${r}="","",IF(COUNTIF($DZ$4:$DZ$4,$G${r})<>1,"",IF(${present}=0,"",${value})))`;
};
const task = (r) => {
  const p = r - 1;
  // Extend the original demand style, without transferring old orders or output.
  for (const [c, cell] of Object.entries(layout.rows["15"].cells)) {
    if (c.length === 1 || c <= "AX")
      sh.getRange(`${c}${r}`).format = nativeStyle(layout.styles[cell.style]);
  }
  sh.getRange(`A${r}:DJ${r}`).format.rowHeight = 18;
  for (const c of ["G", "I", "J", "Q", "R", "S", "E", "AS"])
    sh.getRange(`${c}${r}`).setNumberFormat("@");
  for (const c of ["K", "L", "M", "N", "O", "AW", "AX"])
    sh.getRange(`${c}${r}`).setNumberFormat("#,##0");
  for (const c of ["Z", "AA", "AB", "AG", "AH", "AJ"])
    sh.getRange(`${c}${r}`).setNumberFormat("m/d hh:mm");
  for (const [c, index] of Object.entries({
    H: 2,
    F: 3,
    O: 4,
    T: 5,
    U: 6,
    W: 7,
    AU: 8,
    AV: 9,
    D: 10,
    AC: 11,
    AD: 12,
  }))
    sh.getRange(`${c}${r}`).formulas = [[lookup(r, index)]];
  const f = {
    B: `=IF(A${p}="待排区","",IF(A${p}<>"",A${p},B${p}))`,
    C: `=IF(COUNT(AH${r})>0,AH${r},C${p})`,
    M: `=IF(G${r}="","",SUM(AW${r}:AX${r},BA${r}:DJ${r}))`,
    N: `=IF(G${r}="","",IF(COUNT(L${r},M${r})<2,"",MAX(0,L${r}-M${r})))`,
    V: `=IF(COUNT(N${r},T${r})<2,"",N${r}*T${r}/1000*(1+$EM$2))`,
    X: `=IF(COUNT(N${r},W${r})<2,"",N${r}*W${r})`,
    AE: `=IF(OR(G${r}="",A${p}<>"",B${r}<>B${p}),0,IF(G${r}=G${p},IF(Q${r}=Q${p},0,AD${r}),AC${r}+IF(Q${r}=Q${p},0,AD${r})))`,
    AG: `=IF(OR(G${r}="",B${r}="",B${r}="填写机号",COUNT($I$2)=0,COUNT(O${r})=0,O${r}<=0),"",MAX($I$2,C${p})+AE${r})`,
    AH: `=IF(OR(COUNT(AG${r},N${r},O${r})<3,O${r}<=0),"",AG${r}+N${r}/O${r})`,
    AI: `=IF(COUNT(AH${r})=0,"",YEAR(AH${r})&"/"&MONTH(AH${r}))`,
    AJ: `=IF(COUNT(AH${r})=0,"",AH${r}+$EM$1)`,
    AK: `=IF(COUNT(AB${r},AJ${r})<2,"",AB${r}-AJ${r})`,
    AM: `=IF(OR(COUNT(N${r},O${r})<2,O${r}<=0),"",N${r}/O${r})`,
  };
  for (const [c, formula] of Object.entries(f))
    sh.getRange(`${c}${r}`).formulas = [[formula]];
};
for (let i = 0; i < spec.machineSlots; i++) {
  const r = 4 + i * 6;
  sh.getRange(`A${r}:DJ${r}`).format = {
    fill: "#00FFFF",
    font: { name: "宋体", size: 9, color: "#000000", bold: true },
    rowHeight: 20,
  };
  sh.getRange(`A${r}`).values = [["填写机号"]];
  sh.getRange(`A${r}`).setNumberFormat("@");
  sh.getRange(`A${r}`).dataValidation = {
    rule: { type: "list", formula1: "$EN$4:$EN$4" },
  };
  sh.getRange(`B${r}`).formulas = [[`=A${r}`]];
  sh.getRange(`C${r}`).values = [[0]];
  for (const [column, index] of Object.entries({
    G: 2,
    H: 3,
    I: 4,
    J: 5,
    L: 6,
    Q: 7,
  })) {
    // Excel COUNTIF coerces numeric-looking text (01 equals 1). Prefix only the
    // hidden lookup keys; displayed machine codes and dropdown values stay intact.
    sh.getRange(`${column}${r}`).formulas = [
      [
        `=IF(COUNTIF($EO$4:$EO$4,"M:"&$A${r})<>1,"",IF(VLOOKUP("M:"&$A${r},$EO$4:$EU$4,${index},FALSE)="","",VLOOKUP("M:"&$A${r},$EO$4:$EU$4,${index},FALSE)))`,
      ],
    ];
  }
  // The visible label uses the original band; no new technical column is introduced.
  for (let j = 1; j < 6; j++) task(r + j);
  if (i % 20 === 0) console.log("Authored machine block", i);
}
sh.getRange(`A${pending}:DJ${pending}`).format = {
  fill: "#D9EAD3",
  rowHeight: 22,
  font: { bold: true },
};
sh.getRange(`A${pending}`).values = [["待排区"]];
sh.getRange(`C${pending}`).values = [[0]];
sh.getRange(`G${pending}`).values = [["待排区"]];
for (let r = pending + 1; r <= last; r++) task(r);
sh.freezePanes.freezeRows(3);
sh.freezePanes.freezeColumns(19);
// A compact, in-sheet guide below the blank plan is the only added visible text.
const notes = [
  "填写：厂区由下载入口固定带入，在 I2 填固定排期起点。青色机台行可从本厂设备下拉选择原机号，B1 和 1 分别识别。",
  "排机：只在青色行维护机号，下面任务行自动继承。按从上到下排队；未排机任务放到待排区。可在组内插入整行并复制同组公式。",
  "模具：工模填写公共库模号。名称、机型、日目标、重量和价格从随下载带入的公共资料查找，缺失时留空，可按本单实际填写。",
  "产量：AW、AX 记录本期开始前累计已啤，右侧按日期填白班和夜班实际啤数。M 自动汇总，不重复填期初与本期产量。",
  "日期：右侧从排期起点起预留 31 天。已有记录时不要修改起点重新解释日期；换期请结转期初已啤并清空本期班次格。",
  "导入：在对应厂区上传、检查预览、确认。按机台分组和行顺序保存计划，实际开工仍需在系统操作。",
  "识别：系统按工模、单号、货号、颜色、色粉、用料识别同一需求，调整位置或数量不重复建单。相同身份不要分成多行，拆批在系统处理。",
  "计算：欠数=MAX(0,订单数－已啤数)，啤货天数=欠数÷日目标。料重包含材料附加系数。Excel 日期为连续生产参考，系统保存时结合班历和设备占用重算。",
  "原表参考：华兴啤机日排版表9.1.xlsx 的计划表。原跨周辅助值和查错列不再驱动新排期；其他原业务列的位置保持。",
];
for (const [i, note] of notes.entries()) {
  sh.getRange(`A${last + 3 + i}:AX${last + 3 + i}`).merge();
  sh.getRange(`A${last + 3 + i}`).values = [[note]];
  sh.getRange(`A${last + 3 + i}:AX${last + 3 + i}`).format = {
    font: { name: "宋体", size: 10 },
    rowHeight: 22,
  };
}
// Empty template formula results must remain blank, including zero-vs-missing boundaries.
wb.recalculate();
assert.equal(sh.getRange("N5").values[0][0], "");
console.log(
  (
    await wb.inspect({
      kind: "match",
      searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!",
      options: { useRegex: true, maxResults: 10 },
      summary: "formula errors",
    })
  ).ndjson,
);
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(`${outputDir}/injection-plan-huaxing-v2.xlsx`);
await fs.writeFile(
  `${outputDir}/template-view.png`,
  new Uint8Array(
    await (
      await wb.render({ sheetName: "计划表", range: "A1:BH16", scale: 1.5 })
    ).arrayBuffer(),
  ),
);
console.log(
  "Template authored with original Huaxing column order and styling.",
);
