/**
 * 华兴 发票生成：解析《发票记录原件.xlsx》（11 个客户 sheet，表头在第 1 行、列位各异，
 * header 驱动解析）或各客排期表原件投喂（parseHxgFeed：每客一个文件，按特征 sheet
 * 识别客户——「已出发票（HK抬头）」=迪奇、「出货发票」=buzz，表头行在前 10 行自动定位，
 * 行解析与记录原件同路径）→ 按内置空模板（public/hx-tpl/，由《各客模板发票》5 本文员样票簿
 * 清理而来，见 scripts/hx-build-tpl.mjs）生成发票，每个客户一个输出文件。
 * 多文件混合上传用 mergeHxgParsed 合并：同票号内容不一致时以排期表为准并给 feedDiff 警告；
 * 加密文件由 hxgEncryptedWarning 出提示（本次不解析加密排期表）。
 *
 * 规则来源（2026-10-13 样票逐格比对 + 用户修订口径）：
 *  - 所有客户票面单价 = 记录单价 × 0.967（用户明确：华兴全部发票都乘 0.967，与其他厂区
 *    一致；国际/贸易簿样票虽不打折，以用户口径为准）。SHUSHUPAPA 备注「剩余70%发票」的
 *    行在 ×0.967 基础上再 ×0.7。HK$ 客户在 ×0.967 之后继续 Less。
 *  - 票面写法按版式：f967（H=K*0.967 公式，K 列镜像原价）/ plain967（乘好的定值，思信SCL）/
 *    amt967（buzz：单价列填原价，金额列 =E*H*0.967）/ plain+disc967（国际/贸易）。
 *  - 彩星票面底部 Less:0.5% + Less:4%（均按 Total 计），TOTAL=J42-J44-J45，
 *    与记录"折后单价=原价×0.955"对应（0.967 是票面惯例折扣，0.955 是客户折扣）。
 *  - 迪奇无样票：借同簿 Sheet2（彩星版式，HK$），Less 行按记录 金额HK$折后/原价 比率
 *    反推（×0.95 → Less:5%；×0.95×0.97 → Less:5% + Less:3% 连扣），逐票警告人工核对。
 *  - 思信两个票型：票号 SCL 开头 → Sheet1 版式（单价定值=原价×0.967，无 Less）；
 *    数字票号 → 施信准版式（H=K*0.967 公式，右侧 K 列镜像原价）。施信准5%/施信其它/施信模
 *    三个变体在当前记录里找不到触发证据，只清成空模板，不自动使用（页面有提示）。
 *  - 思信货号按样票（示例编号）惯例去 "-XX"/"混装" 后缀；"X混装"父行（价0）+ 同基价相同的
 *    "-XX" 子行合并为一行（货号=基号、数量=父行数量、单价=子行单价）；子行单价不一致
 *    （如 示例编号 的 示例编号混装）不合并，整组原样保留并警告。
 *  - S/N 合约号码一律写记录里的完整原串（CC810、W-示例编号、示例编号 等含字母
 *    连字符的号码不截断）；一票多合同号时只写第一个并给 snMulti 警告（用户要求，取代
 *    样票"只写数字"的做法）。货号一律按文本写入，长数字货号不会显示成 1E+09。
 *  - 迪士尼样票（香港簿 Sheet1，示例编号）：样票货号 示例编号 与记录货号 示例编号
 *    不一致（文员手改海关备案号），按记录货号生成并警告。
 *  - 每张票在明细表头行高度、打印区域右方第二列（refCell）用红色字体写该票记录原始总金额
 *    （未打折记录合计），供文员核对（红样式由模板构建时注入）。
 *  - EDU 版式特殊：D=货号首段、E=货号次段（样票 F12/BN328 与 F12/MK050 推定），I=+L*0.967、
 *    K=I*F、L=原价镜像，合计在 K46。原簿 EDU/施信其它/施信模 三张样票没有抬头单元格
 *    （strings 级确认 .xls 里就没有），保持原样不补，页面提示。
 *  - 抬头按《华兴发票抬头.xlsx》权威映射逐字符覆写（含尾随空格）：香港（迪奇/彩星/迪士尼）、
 *    亚洲（buzz/EDU）、康宜（思信）、国际（MAXX/银辉）、贸易（360/MMI/SHUSHUPAPA）。
 *    香港簿 Sheet1、康宜簿 施信准/施信准5% 样票抬头是错的（INTERNATIONAL），生成时覆写。
 *  - 不带抬头使用《大陆格式.xls》的“有打印纸格式”套打，连同字段标签、买方及列标题都不打印，
 *    合同号/票号/日期分别在J7/J9/J13，明细E22:K45，合计K46；沿用各客户原计算规则。
 *  - 明细超模板容量拆续票（sheet 名 基号、基号-1…），非末页合计留空，末页跨页汇总。
 *  - 模板内置 A4 纵向 fitToPage（一页一张），打印区域精确到合计行。
 *  - 其他款/模具费（extra，2026-10-20）：投喂排期表时同时解析该客「其它款/其他费/模具手办费」
 *    类 sheet（HXG_EXTRA_PARSERS），票对象带 extra/extraKind/currency，与货款票同数组流转
 *    （去重键带 extra 标记）；生成时按客户格式组分流到第二个文件「华兴_X其他款及模费发票.xlsx」
 *    （完整格式用《其他以及模具费用类型》3 本模板，套打统一用“有打印纸格式”定位）。
 *    其他款=单价×0.967（pp/trade 带原价镜像），模具费=全额不打折按金额列开票。
 *
 * 纯 ESM，浏览器 / Node 通用。
 */

import * as XLSX from 'xlsx';
import { XlsxPackage } from './xlsxPackage.js';
import { colToIdx, idxToCol, cellXml, styleOf, parseRows, rowXml } from './sheetBuilder.js';

const { cNum, cStr, cEmpty, cFormula } = cellXml;

/** 权威抬头映射（《华兴发票抬头.xlsx》逐字符，含尾随空格） */
export const HXG_HEADERS = {
  '香港': 'ROYAL REGENT PRODUCTS (H.K) LIMITED ',
  '亚洲': 'ROYAL REGENT PRODUCTS (ASIA) LIMITED',
  '康宜': 'CONRY LIMITED',
  '国际': 'ROYAL REGENT PRODUCTS INTERNATIONAL LIMITED',
  '贸易': 'ROYAL REGENT PRODUCTS TRADING LTD.',
};

export const HXG_PREPRINTED_TPL = '华兴-套打.xlsx';

/** 预印纸使用参考文件的固定坐标；金额规则仍取原客户票型。 */
function preprintedLayout(original) {
  const totals = { ...original.totals, grandRow: 46, valCol: 11, curCol: 10, labelCol: 9 };
  let detailTo = 45;
  if (totals.kind === 'less2') {
    detailTo = 41;
    Object.assign(totals, { subRow: 42, lessRows: [43, 44] });
  } else if (totals.kind === 'disc5') {
    detailTo = 42;
    Object.assign(totals, { subRow: 43, discRow: 44 });
  } else if (totals.kind === 'intl') {
    detailTo = 41;
    Object.assign(totals, { subRow: 42, periodRows: [43, 44, 45] });
  }
  return {
    ...original, preprinted: true, sheet: '有打印纸格式', buyerCell: null,
    snCell: 'J7', noCell: 'J9', dateCell: 'J13', noAsNumber: false,
    detailFrom: 22, detailTo, maxCol: 14,
    cols: { desc: 5, qty: 6, pcs: 7, cur1: 8, price: 9, cur2: 10, amt: 11, orig: 12 },
    // 套打纸的货号只有一列，完整保留原货号；含70%/30%的单价写实际计算值。
    splitCode: false, priceRefOrig: false,
    refCell: 'M21', headCells: [], totals,
  };
}

/**
 * 版式配置（生成与模板清理共用，scripts/hx-build-tpl.mjs 也读这里）。
 * cols 列位为 1-based 列号：desc 货号 / desc2 货号次段(EDU) / qty 数量 / pcs 单位 /
 * cur1 cur2 币种 / price 单价 / amt 金额 / orig 右侧原价镜像。
 * totals.kind: sum 单行合计 | less2 Total+两行Less+TOTAL | disc5 SubTotal+5%+TOTAL |
 *              intl 合计行42+TOTAL行46（首期50%行仅 inv.firstPeriod 时填）。
 */
export const HXG_VARIANTS = {
  // 香港簿 Sheet2：彩星样票 示例编号
  cxhk: {
    book: '香港（迪奇、彩星、迪士尼）', sheet: 'Sheet2', label: '香港簿Sheet2（彩星版式）',
    buyerCell: 'A17', snCell: 'I9', noCell: 'I12', dateCell: 'I15', noAsNumber: false,
    detailFrom: 22, detailTo: 41, maxCol: 14,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967',
    totals: { kind: 'less2', subRow: 42, lessRows: [44, 45], grandRow: 48, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: 'L21', headCells: ['C1', 'C2', 'D3', 'C4', 'D7', 'D10'],
    strays: [],
  },
  // 香港簿 Sheet1：迪士尼样票 示例编号（抬头错 INTERNATIONAL，生成覆写）
  dsn: {
    book: '香港（迪奇、彩星、迪士尼）', sheet: 'Sheet1', label: '香港簿Sheet1（迪士尼版式）',
    buyerCell: 'A4', snCell: 'I3', noCell: 'I4', dateCell: 'I6', noAsNumber: true,
    detailFrom: 12, detailTo: 36, maxCol: 14,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11 },
    currency: 'USD', pcs: 'PCS', priceMode: 'f967',
    totals: { kind: 'sum', grandRow: 37, valCol: 10, curCol: 9 },
    refCell: 'L11', headCells: [],
    strays: ['K6', 'K11', 'L11'],
  },
  // 亚洲簿 Sheet1：buzz 样票 示例编号（单行贴纸票，金额列才乘 0.967）
  buzz: {
    book: '亚洲（BUZZ、EDU）', sheet: 'Sheet1', label: '亚洲簿Sheet1（buzz版式）',
    buyerCell: 'A17', snCell: 'I9', noCell: 'I12', dateCell: 'I15', noAsNumber: true,
    detailFrom: 22, detailTo: 47, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'HK$', pcs: 'PCS', priceMode: 'amt967',
    totals: { kind: 'sum', grandRow: 48, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: 'L21', headCells: ['C1', 'C2', 'D3', 'C4', 'D7', 'D10'],
    strays: [],
  },
  // 亚洲簿 EDU：样票 示例编号
  edu: {
    book: '亚洲（BUZZ、EDU）', sheet: 'EDU', label: '亚洲簿EDU',
    buyerCell: null, snCell: null, noCell: 'J9', dateCell: 'J13', noAsNumber: true,
    detailFrom: 22, detailTo: 45, maxCol: 17,
    cols: { desc: 4, desc2: 5, qty: 6, pcs: 7, cur1: 8, price: 9, cur2: 10, amt: 11, orig: 12 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967', splitCode: true,
    totals: { kind: 'sum', grandRow: 46, valCol: 11, curCol: 10 },
    refCell: 'M21', headCells: [],
    strays: ['L18', 'N18', 'E11'],
  },
  // 亚洲簿 EDU (其它款)：样票 RR0002（不自动使用）
  eduoth: {
    book: '亚洲（BUZZ、EDU）', sheet: 'EDU (其它款)', label: '亚洲簿EDU(其它款)',
    buyerCell: null, snCell: null, noCell: 'J9', dateCell: 'J13', noAsNumber: false,
    detailFrom: 22, detailTo: 45, maxCol: 17,
    cols: { desc: 4, desc2: 5, qty: 6, pcs: 7, cur1: 8, price: 9, cur2: 10, amt: 11, orig: 12 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967', splitCode: true,
    totals: { kind: 'sum', grandRow: 46, valCol: 11, curCol: 10 },
    refCell: 'M21', headCells: [],
    strays: ['L18', 'N18', 'E11'],
  },
  // 康宜簿 Sheet1：思信 SCL 样票 示例编号（单价/金额都是乘好的定值）
  sxscl: {
    book: '康宜（思信）', sheet: 'Sheet1', label: '康宜簿Sheet1（SCL版式）',
    buyerCell: 'A17', snCell: null, noCell: 'I12', dateCell: 'I15', noAsNumber: false,
    detailFrom: 22, detailTo: 47, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'HK$', pcs: 'PCS', priceMode: 'plain967',
    totals: { kind: 'sum', grandRow: 48, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: 'L21', headCells: ['A1', 'A2', 'A3', 'A4', 'D7', 'D10'],
    strays: [],
  },
  // 康宜簿 施信准：思信数字票号样票 示例编号（抬头错 INTERNATIONAL，生成覆写）
  sxstd: {
    book: '康宜（思信）', sheet: '施信准', label: '康宜簿施信准',
    buyerCell: 'A11', snCell: null, noCell: 'H10', dateCell: 'I11', noAsNumber: true,
    detailFrom: 17, detailTo: 42, maxCol: 15,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967',
    totals: { kind: 'sum', grandRow: 43, valCol: 10, curCol: 9 },
    refCell: 'L16', headCells: [],
    strays: ['H7', 'I7', 'J7', 'D10', 'L11', 'K13', 'O13', 'O14', 'M33', 'L43'],
  },
  // 康宜簿 施信准5%：样票 示例编号（不自动使用；Sub Total + 5% Discount）
  sxstd5: {
    book: '康宜（思信）', sheet: '施信准5%', label: '康宜簿施信准5%',
    buyerCell: 'A12', snCell: null, noCell: 'I9', dateCell: 'I12', noAsNumber: false,
    detailFrom: 18, detailTo: 39, maxCol: 15,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967',
    totals: { kind: 'disc5', subRow: 40, discRow: 41, grandRow: 44, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: 'L17', headCells: [],
    strays: ['I6', 'J6', 'H7', 'I7', 'J7', 'D11', 'L12', 'K14', 'M14'],
  },
  // 康宜簿 施信其它：样票 示例编号（不自动使用；原价镜像在 L 列）
  sxoth: {
    book: '康宜（思信）', sheet: '施信其它', label: '康宜簿施信其它',
    buyerCell: null, snCell: null, noCell: 'I11', dateCell: 'I14', noAsNumber: false,
    detailFrom: 20, detailTo: 43, maxCol: 14,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 12 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967',
    totals: { kind: 'sum', grandRow: 44, valCol: 10, curCol: 9 },
    refCell: 'L19', headCells: [],
    strays: ['K18', 'L18', 'D12'],
  },
  // 康宜簿 施信模：样票 示例编号（不自动使用；模款全额不打折，单位 SET）
  sxmold: {
    book: '康宜（思信）', sheet: '施信模', label: '康宜簿施信模',
    buyerCell: null, snCell: null, noCell: 'I11', dateCell: 'I14', noAsNumber: false,
    detailFrom: 21, detailTo: 43, maxCol: 14,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'HK$', pcs: 'SET', priceMode: 'plain',
    totals: { kind: 'sum', grandRow: 44, valCol: 10, curCol: 9 },
    refCell: 'L20', headCells: [],
    strays: ['I9', 'K19', 'D12'],
  },
  // 国际簿 国际有限公司：MAXX 样票 示例编号（首期50%模款票，单位 SET；货款票按 PCS 生成）。
  // 样票 K 列是 0.449 帮手列（非原价镜像），明细不写 orig。
  intl: {
    book: '国际（MAXX、银辉）', sheet: '国际有限公司', label: '国际簿',
    buyerCell: 'A16', snCell: 'I10', noCell: 'J13', dateCell: 'I15', noAsNumber: false,
    detailFrom: 21, detailTo: 41, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'USD', pcs: 'PCS', priceMode: 'plain', disc967: true,
    refCell: 'L17', headCells: ['A1', 'A2', 'A3', 'A4', 'D7', 'D10'],
    totals: { kind: 'intl', subRow: 42, grandRow: 46, valCol: 10, curCol: 9, labelCol: 8, periodRows: [43, 44, 45] },
    strays: ['L18', 'L19', 'L45'],
  },
  // 贸易簿 360：样票 示例编号（H==K21 参照原价列，不打折；360/MMI/SHU SHU PAPA 共用）
  trade: {
    book: '贸易（360、MMI、SHU SHU PAPA）', sheet: '360', label: '贸易簿360版式',
    buyerCell: 'A16', snCell: 'I10', noCell: 'J13', dateCell: 'I15', noAsNumber: false,
    detailFrom: 21, detailTo: 47, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11 },
    currency: 'USD', pcs: 'PCS', priceMode: 'plain', priceRefOrig: true, disc967: true,
    refCell: 'L17', headCells: ['A1', 'A2', 'A3', 'A4', 'D7', 'D10'],
    totals: { kind: 'sum', grandRow: 48, valCol: 10, curCol: 9, labelCol: 8 },
    strays: ['K20', 'L18', 'L19'],
  },
  /* —— 其他款/模具费变体（《其他以及模具费用类型》3 本样票簿；模板本身分格式，
   *    headCells 全空：不随「包含公司抬头」开关清空。样票 S/N 全空 → 生成也只清空不写） —— */
  // 有打印纸簿 其他款：样票 示例编号（思信）/示例编号（迪奇）/示例编号（buzz），单价=原价×0.967，L 列镜像原价
  ppOther: {
    book: '大陆发票--有打印纸格式', sheet: '其他款施信', label: '其他款（有打印纸版式）',
    buyerCell: null, snCell: 'J7', noCell: 'J9', dateCell: 'J13', noAsNumber: true,
    detailFrom: 22, detailTo: 45, maxCol: 12,
    cols: { desc: 5, qty: 6, pcs: 7, cur1: 8, price: 9, cur2: 10, amt: 11, orig: 12 },
    currency: 'HK$', pcs: 'PCS', priceMode: 'f967',
    totals: { kind: 'sum', grandRow: 46, valCol: 11, curCol: 10 },
    refCell: null, headCells: [],
    strays: [],
  },
  // 有打印纸簿 模费：样票 示例编号（思信）/示例编号（迪奇）/示例编号（buzz），全额不打折、无镜像列
  ppMold: {
    book: '大陆发票--有打印纸格式', sheet: '模费施信', label: '模具费（有打印纸版式）',
    buyerCell: null, snCell: 'J7', noCell: 'J9', dateCell: 'J13', noAsNumber: true,
    detailFrom: 22, detailTo: 45, maxCol: 12,
    cols: { desc: 5, qty: 6, pcs: 7, cur1: 8, price: 9, cur2: 10, amt: 11, orig: null },
    currency: 'HK$', pcs: 'PCS', priceMode: 'plain',
    totals: { kind: 'sum', grandRow: 46, valCol: 11, curCol: 10 },
    refCell: null, headCells: [],
    strays: [],
  },
  // 国际簿 其他款：无数据样票（只有 L18「*7.75」备注），按用户口径 ×0.967 定值、无镜像
  intlOther: {
    book: '大陆发票--国际打印格式', sheet: '其他款', label: '其他款（国际版式）',
    buyerCell: 'A16', snCell: 'I9', noCell: 'J13', dateCell: 'I15', noAsNumber: false,
    detailFrom: 21, detailTo: 46, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'USD', pcs: 'PCS', priceMode: 'plain967',
    totals: { kind: 'sum', grandRow: 47, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: null, headCells: [],
    strays: ['L18'],
  },
  // 国际簿 模费：样票 示例编号（银辉，HK$、SET、全额不打折；R40「工模」残留在明细区内自动清）
  intlMold: {
    book: '大陆发票--国际打印格式', sheet: '模费', label: '模具费（国际版式）',
    buyerCell: 'A16', snCell: 'I9', noCell: 'J13', dateCell: 'I15', noAsNumber: false,
    detailFrom: 21, detailTo: 46, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'HK$', pcs: 'SET', priceMode: 'plain',
    totals: { kind: 'sum', grandRow: 47, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: null, headCells: [],
    strays: [],
  },
  // 贸易簿 其他款：样票 示例编号（360；H=K*0.967，K 列镜像原价；样票 L 列双镜像按 K 只写一列）
  tradeOther: {
    book: '大陆格式--贸易打印格式', sheet: '其他款', label: '其他款（贸易版式）',
    buyerCell: 'A16', snCell: 'I9', noCell: 'J12', dateCell: 'I15', noAsNumber: false,
    detailFrom: 21, detailTo: 45, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: 11 },
    currency: 'USD', pcs: 'SET', priceMode: 'f967',
    totals: { kind: 'sum', grandRow: 46, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: null, headCells: [],
    strays: ['L18'],
  },
  // 贸易簿 模款：样票 示例编号（360；数量×单价=全额 全额不打折、无镜像）
  tradeMold: {
    book: '大陆格式--贸易打印格式', sheet: '模款', label: '模具费（贸易版式）',
    buyerCell: 'A16', snCell: 'I9', noCell: 'J12', dateCell: 'I15', noAsNumber: false,
    detailFrom: 21, detailTo: 45, maxCol: 12,
    cols: { desc: 4, qty: 5, pcs: 6, cur1: 7, price: 8, cur2: 9, amt: 10, orig: null },
    currency: 'USD', pcs: 'SET', priceMode: 'plain',
    totals: { kind: 'sum', grandRow: 46, valCol: 10, curCol: 9, labelCol: 8 },
    refCell: null, headCells: [],
    strays: [],
  },
};

/**
 * 客户配置：记录 sheet 列位（header 名归一化后匹配，occ=同名第几次出现）、模板、抬头组。
 * colspec 值：字符串 = 归一化精确匹配；{ re } = 正则；{ name, occ } = 精确匹配第 occ 次。
 */
/**
 * 「有打印纸」客户（大陆格式.xls 备注 sheet 清单）：思信（康宜）、迪奇/彩星/迪士尼（香港）、
 * buzz/EDU（亚洲）——这些客的打印纸自带抬头和表头，自动模式使用套打（noHead）。
 * 国际（MAXX、银辉）/贸易（360、MMI、SHU SHU PAPA）默认要抬头。
 * 页面打印格式默认逐客户自动判定，用户手动选择完整格式或套打时优先。
 */
export const HXG_NOHEAD_CUSTOMERS = new Set(['思信', '迪奇', '彩星', '迪士尼', 'buzz', 'EDU']);
export const HXG_CUSTOMERS = {
  'buzz': {
    tplFile: '华兴-buzz.xlsx', variant: 'buzz', header: '亚洲',
    // buyer 客名（WM 票判定用）；netPrice「验货报告」列=净价（原价−降价差额），其右一列（无表头）=降价差额
    cols: { date: '打票日期', no: '发票号', code: '產品編號', qty: '數量', price: '单价', amt: '金额HKD', discAmt: { re: /^金额HKD（蓝色字体为折扣）/ }, sn: 'PO.NO', buyer: '客名/國家', netPrice: '验货报告' },
  },
  '迪奇': {
    tplFile: '华兴-香港.xlsx', variant: 'cxhk', header: '香港',
    cols: { date: '打票日期', no: '发票号NO.', code: '產品編號', qty: '數量', price: '单价', amt: { name: '金额HK$', occ: 1 }, discAmt: { name: '金额HK$', occ: 2 }, sn: 'Reference' },
  },
  '思信': {
    tplFile: '华兴-思信.xlsx', variant: 'auto-sixin', header: '康宜',
    cols: { date: '出票日期', no: '发票号', code: '產品編號', qty: '數量', price: '单价HK$', amt: '金额' },
  },
  '彩星': {
    tplFile: '华兴-香港.xlsx', variant: 'cxhk', header: '香港',
    cols: { date: '出票日期', no: '发票号', code: '產品編號', qty: '數量', price: '原价单价', amt: '原价总金额', discAmt: '折后金额', sn: '预备单号' },
  },
  'EDU': {
    tplFile: '华兴-EDU.xlsx', variant: 'edu', header: '亚洲',
    cols: { date: '打票日期', no: '发票号NO.', code: '產品編號', qty: '數量', price: '单价', amt: '金额HK$' },
  },
  '360': {
    tplFile: '华兴-贸易.xlsx', variant: 'trade', header: '贸易',
    cols: { date: '打票日期', no: 'INVOICE', code: '產品編號', qty: 'PO数量', price: { re: /^单价/ }, amt: { re: /^TOTAL（USD）/ }, sn: '主合同号' },
  },
  'MAXX': {
    tplFile: '华兴-国际.xlsx', variant: 'intl', header: '国际',
    cols: { date: 'DATE', no: '发票号码NO.', code: 'ITEM', qty: 'QTY', price: { re: /^单价/ }, amt: 'TOTAL', sn: 'P.O.NO.' },
  },
  '迪士尼': {
    tplFile: '华兴-香港.xlsx', variant: 'dsn', header: '香港',
    cols: { date: '打票日期', no: '发票号', code: '货号', qty: 'PO数量', price: '单价USD', amt: 'TOTAL（USD）', sn: '合同号' },
  },
  'SHUSHUPAPA': {
    tplFile: '华兴-贸易.xlsx', variant: 'trade', header: '贸易',
    cols: { date: '发票日期', no: '发票号码', code: 'ITEMNO.', qty: '走货数量', price: { re: /^单价/ }, amt: '走货金额USD', sn: '采购订单NO.', note: '备注' },
  },
  '银辉': {
    tplFile: '华兴-国际.xlsx', variant: 'intl', header: '国际',
    cols: { date: '打票日期', no: 'INVOICE', code: '產品編號', qty: 'PO数量', price: '单价USD', amt: 'TOTAL（USD）', sn: '银辉合同号' },
  },
  'MMI': {
    tplFile: '华兴-贸易.xlsx', variant: 'trade', header: '贸易',
    cols: { date: '出票日期', no: '发票号', code: '產品編號', qty: '數量', price: '单价US$', amt: '金额US$', sn: 'PO.NO' },
  },
};

/** 客户 → 模板文件里要用到的 sheet（模板文件名 → [变体...]），build 脚本与页面共用 */
export const HXG_TPL_SHEETS = {
  '华兴-buzz.xlsx': ['buzz'],
  '华兴-EDU.xlsx': ['edu', 'eduoth'],
  '华兴-思信.xlsx': ['sxscl', 'sxstd', 'sxstd5', 'sxoth', 'sxmold'],
  '华兴-香港.xlsx': ['cxhk', 'dsn'],
  '华兴-国际.xlsx': ['intl'],
  '华兴-贸易.xlsx': ['trade'],
  '华兴-其他款模费-打印纸.xlsx': ['ppOther', 'ppMold'],
  '华兴-其他款模费-国际.xlsx': ['intlOther', 'intlMold'],
  '华兴-其他款模费-贸易.xlsx': ['tradeOther', 'tradeMold'],
};

/** 其他款/模具费（extra）：客户 → 格式组（pp=有打印纸 / intl=国际 / trade=贸易）。
 *  与 HXG_NOHEAD_CUSTOMERS 同口径：香港/亚洲/康宜组用打印纸，MAXX/银辉国际，360/MMI/SHUSHUPAPA 贸易。 */
export const HXG_EXTRA_FORMAT = {
  '思信': 'pp', '迪奇': 'pp', '彩星': 'pp', '迪士尼': 'pp', 'buzz': 'pp', 'EDU': 'pp',
  'MAXX': 'intl', '银辉': 'intl',
  '360': 'trade', 'MMI': 'trade', 'SHUSHUPAPA': 'trade',
};
/** 格式组 → 模板文件 / 变体 */
export const HXG_EXTRA_TPL = {
  pp: '华兴-其他款模费-打印纸.xlsx',
  intl: '华兴-其他款模费-国际.xlsx',
  trade: '华兴-其他款模费-贸易.xlsx',
};
const HXG_EXTRA_VARIANT = {
  pp: { other: 'ppOther', mold: 'ppMold' },
  intl: { other: 'intlOther', mold: 'intlMold' },
  trade: { other: 'tradeOther', mold: 'tradeMold' },
};

const trim = (v) => (v === null || v === undefined ? '' : String(v).trim());
const numOrNull = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = +v;
  return Number.isFinite(n) ? n : null;
};
/** 日期 → Excel 序列号（记录里基本都是序列数，兼容字符串日期） */
function dateSerialOf(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number' && v > 40000 && v < 60000) return Math.round(v);
  if (v instanceof Date) return Math.round(v.getTime() / 86400000 + 25569);
  const m = String(v).match(/(\d{4})\s*[年.\-/]\s*(\d{1,2})\s*[月.\-/]\s*(\d{1,2})/);
  if (m) return Math.round(Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000 + 25569);
  return null;
}
const ymOf = (serial) => {
  if (!serial) return null;
  const d = new Date((serial - 25569) * 86400000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};

/** header 名归一化：去全部空白（中英文空格、换行） */
const normHdr = (v) => String(v ?? '').replace(/\s+/g, '');

function resolveCols(headerRow, spec, sheet, warnings) {
  const cols = {};
  const norm = headerRow.map((c) => normHdr(c));
  for (const [key, s] of Object.entries(spec)) {
    if (s == null) continue; // 投喂排期表缺该列（如 SHUSHUPAPA 无备注列）：跳过
    let idx = null;
    if (typeof s === 'string') {
      idx = norm.findIndex((h) => h === s);
      if (idx < 0) idx = null;
    } else if (s && s.re) {
      idx = norm.findIndex((h) => s.re.test(h));
      if (idx < 0) idx = null;
    } else if (s && s.name) {
      let seen = 0;
      idx = null;
      norm.forEach((h, i) => {
        if (idx === null && h === s.name) { seen++; if (seen === (s.occ ?? 1)) idx = i; }
      });
    }
    if (idx === null) {
      if (['date', 'no', 'code', 'qty', 'price'].includes(key))
        warnings.push({ type: 'colMiss', sheet, text: `${sheet}：表头里找不到「${typeof s === 'string' ? s : s.name || s.re}」列（${key}），该 sheet 跳过` });
      return null;
    }
    cols[key] = idx;
  }
  return cols;
}

/** 思信货号基号：截断到第一个 "-" 或 "混装"（样票 示例编号 惯例：示例编号→示例编号、示例编号混装→示例编号） */
export function sixinBaseCode(code) {
  return String(code ?? '').trim().split(/[-混装]/)[0].trim();
}

// 源排期确认的跨货号配件对应；不能把同一张票的其他零价产品都视作子行。
const SIXIN_COMPONENTS = {
  W80230: new Set(['Z28288-01-A', 'Z28288-01-B']),
  W82684: new Set(['Z28288-01-A', 'Z28288-01-B']),
  W89791: new Set(['W85569', 'W83959']),
  W89777: new Set(['W83762-01', 'W83765-01', 'W84496-01']),
};
function sixinSameOrder(parent, child) {
  let matches = 0;
  for (const key of ['sourcePo', 'sourceContract', 'sourceReference']) {
    const a = parent[key], b = child[key];
    if (a && b) {
      if (a !== b) return false;
      matches++;
    }
  }
  return matches > 0;
}
function sixinChildOf(parent, child) {
  if (!parent || /混装/.test(trim(child.code))) return false;
  const base = sixinBaseCode(parent.code), code = trim(child.code);
  // 同基号“-款式”本身是明确的结构证据，但有订单身份冲突时不归并。
  if (code.startsWith(base + '-')) {
    return !['sourcePo', 'sourceContract', 'sourceReference'].some((key) => parent[key] && child[key] && parent[key] !== child[key]);
  }
  return !!SIXIN_COMPONENTS[base]?.has(code) && sixinSameOrder(parent, child);
}

/** 思信行变换：逐个混装组识别父子行。已确认的零额配件不上票面；
 *  非子行的零价/缺价行及有金额的行保留，不能靠“整票有混装”或单个 0 判子行。 */
function transformSixinLines(inv, warnings) {
  const out = [];
  const lines = inv.lines;
  let mixParent = null;
  const dropped = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const code = trim(l.code);
    const base = sixinBaseCode(code);
    if (/混装/.test(code)) {
      mixParent = l;
      const children = [];
      let j = i + 1;
      while (j < lines.length && String(trim(lines[j].code)).startsWith(base + '-') && sixinChildOf(l, lines[j])) { children.push(lines[j]); j++; }
      if (children.length) {
        const prices = [...new Set(children.map((c) => c.price))];
        const qtySum = children.reduce((s, c) => s + (c.qty ?? 0), 0);
        // 只有不独立收费的汇总父行才能由有价子行合并；0/0 说明子行不能覆盖父行的价格。
        if (prices.length === 1 && Number.isFinite(prices[0]) && prices[0] > 0
          && children.every((c) => (c.qty ?? 0) > 0) && l.qty !== 0
          && (l.price === 0 || l.price == null) && (l.amt === 0 || l.amt == null)) {
          if (l.qty !== null && Math.abs(l.qty - qtySum) > 1e-9)
            warnings.push({ type: 'mixQty', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `思信 ${inv.invNo}：${code} 父行数量 ${l.qty} ≠ 子行合计 ${qtySum}，已按父行数量合并，请人工核对` });
          out.push({ ...l, kind: 'goods', code: base, qty: l.qty ?? qtySum, price: prices[0], amt: (l.qty ?? qtySum) * prices[0] });
          i = j - 1;
          continue;
        }
        if (prices.length > 1)
          warnings.push({ type: 'mixNoMerge', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `思信 ${inv.invNo}：${code} 子行单价不一致（${prices.join('/')}），未合并，整组原样保留，请人工核对` });
      }
    }
    const isChild = sixinChildOf(mixParent, l);
    // 只移除当前父行下、身份与货号对应均已确认且没有独立金额的配件。
    if (isChild && (l.price === 0 || l.price == null) && (l.amt === 0 || l.amt == null) && (l.qty ?? 0) > 0) {
      dropped.push(code);
      continue;
    }
    if (isChild && (l.qty === 0 || l.qty == null) && (l.price === 0 || l.price == null) && (l.amt === 0 || l.amt == null)) {
      out.push({ ...l, kind: 'note', code, qty: null, price: null, amt: 0 });
      continue;
    }
    if (!/混装/.test(code) && !isChild) mixParent = null;
    out.push({ ...l, code: base || l.code });
  }
  if (dropped.length)
    warnings.push({ type: 'mixZeroDrop', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `思信 ${inv.invNo}：已按父行、货号对应及订单身份确认混装配件/客供行 ${dropped.join('、')}（单价及金额为 0），不上票面，请人工核对` });
  // 源表金额=箱数×单价（金额列公式 L*K，单价是每箱价）的行：amt≠数量×单价，
  // 按 金额÷数量 反推件单价，使票面金额与源表一致（示例编号 每箱 51/6 件→8.5；示例编号 示例编号混装 1259 箱×1.68→0.14）
  for (const l of out) {
    if (l.kind === 'goods' && (l.qty ?? 0) > 0 && (l.price ?? 0) > 0 && typeof l.amt === 'number'
      && Math.abs(l.amt - l.qty * l.price) > 0.011) {
      const implied = +(l.amt / l.qty).toFixed(6);
      warnings.push({ type: 'sixinAmtImply', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `思信 ${inv.invNo}：${l.code} 源表金额 ${l.amt}=箱数×单价（单价 ${l.price} 为每箱价，非每件价），已按件单价 ${implied}（金额÷数量 ${l.qty}）生成，票面金额与源表一致，请人工核对` });
      l.price = implied;
    }
  }
  inv.lines = out;
}

/** 迪奇逐票折扣：记录 折后/原价 比率 → Less 行规格（无样票，生成时逐票警告）。
 *  2026-10 文员新规则：美国票以后不打折（记录 折后=原价，比率≈1）→ 不留 Less 行全额生成；
 *  比率 0.9215 = Less:5%+Less:3%（旧美国票连扣），0.95 = Less:5%。 */
function detectDiqiLess(inv, warnings) {
  const sumK = inv.lines.reduce((s, l) => s + (l.amt ?? 0), 0);
  const sumL = inv.lines.reduce((s, l) => s + (l.discAmt ?? l.amt ?? 0), 0);
  const ratio = sumK > 0 ? sumL / sumK : null;
  if (ratio !== null && Math.abs(ratio - 1) < 0.0015)
    inv.less = [];
  else if (ratio !== null && Math.abs(ratio - 0.9215) < 0.0015)
    inv.less = [{ pct: 0.05, label: 'Less:5%', base: 'sub' }, { pct: 0.03, label: 'Less:3%', base: 'afterLess' }];
  else
    inv.less = [{ pct: 0.05, label: 'Less:5%', base: 'sub' }];
  if (ratio !== null && Math.abs(ratio - 1) >= 0.0015 && Math.abs(ratio - 0.95) >= 0.0015 && Math.abs(ratio - 0.9215) >= 0.0015)
    warnings.push({ type: 'diqiRatio', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `迪奇 ${inv.invNo}：记录折扣比率 ${ratio.toFixed(4)} 不是 1（无折扣）/ 0.95 / 0.9215，已按 Less:5% 生成，请人工核对` });
  if (inv.market === '美国' && ratio !== null && Math.abs(ratio - 1) >= 0.0015)
    warnings.push({ type: 'diqiUsOld', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `迪奇 ${inv.invNo}：美国票按新规则以后不打折，本票记录仍带折扣（比率 ${ratio.toFixed(4)}），已按记录生成，如属新数据请与文员确认` });
  warnings.push({ type: 'diqiNoSample', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `迪奇 ${inv.invNo}：无文员样票，按彩星版式（单价×0.967，${inv.less.length ? inv.less.map((x) => x.label.replace('Less:', 'Less ')).join(' + ') : '全额无 Less 行'}）生成，请人工核对` });
}

/** 市场标记：迪奇=国家列（纯中文国家名，排除厂区「华兴」；国家列在 0.03 折扣列一带，表头与数据错位，按内容扫），
 *  buzz=标准列（美国标准/加拿大标准/欧洲标准）。只取每行第一个命中。 */
function marketOf(sn, r) {
  for (let c = 13; c <= 22; c++) {
    const v = r[c];
    if (typeof v !== 'string' || !v.trim()) continue;
    const s = v.trim();
    if (sn === 'buzz') { if (/标准$/.test(s)) return s; }
    else if (/^[一-龥]+$/.test(s) && s !== '华兴') return s;
  }
  return null;
}

/**
 * 按列位配置解析某个 sheet 的行集 → invoices（仅行级解析，不做客户级后处理）。
 * rows 为 sheet_to_json(header:1) 的全量行，hdrIdx 为表头行下标（0-based），
 * 列位按该表头行的表头名解析（resolveCols）。发票号列为空的行归并到上一票
 * （记录原件路径；投喂路径改按 opts.noColMerges 的合并单元格判定，见下）。
 * parseHxgRecords（合订本，hdrIdx=0）与 parseHxgFeed（单客排期表，表头行自动定位）
 * 共用本函数，避免两份逻辑漂移。
 * opts 仅投喂路径使用：cleanNo 票号清洗（如 MAXX「示例编号\n（10-5已找数）」）、
 * skipRow(r, cols) 跳过汇总行（如思信「X月份/合计HK$:」行）、
 * noColMerges + rowOffset：排期表 sheet 的 !merges 与 !ref 起始行——发票号列为空的行
 * 默认不再归并上一票（buzz 等排期表有大量手输漏填票号的杂行），仅当该行落在
 * 「覆盖发票号列、锚点有票号」的合并单元格内时才继承（彩星/MAXX 的真合并单元格）。
 */
function parseHxgSheetRows(sn, conf, rows, hdrIdx, warnings, opts = {}) {
  const invoices = [];
  if (!rows.length) return invoices;
  const cols = resolveCols(rows[hdrIdx], conf.cols, sn, warnings);
  if (!cols) return invoices;
  // 父子行识别使用逐行订单身份，不把它们当作票面 S/N，也不要求所有来源都有这些列。
  const optionalColumn = (names) => rows[hdrIdx].findIndex((v) => names.includes(normHdr(v).toUpperCase()));
  const identityCols = sn === '思信' ? {
    sourcePo: optionalColumn(['PO.NO', 'P.O.NO.']),
    sourceContract: optionalColumn(['O/CNO', 'O/CNO.']),
    sourceReference: optionalColumn(['预备单号', 'REFERENCE']),
  } : {};
  // 投喂路径：票号列空行仅在「票号列真合并单元格」覆盖范围内才归并上一票
  let noInheritRows = null;
  if (opts.noColMerges && cols.no != null) {
    noInheritRows = new Set();
    const off = opts.rowOffset || 0;
    for (const m of opts.noColMerges) {
      if (cols.no < m.s.c || cols.no > m.e.c || m.e.r <= m.s.r) continue;
      const anchorRow = rows[m.s.r - off];
      if (!anchorRow || !trim(anchorRow[cols.no])) continue;
      for (let rr = m.s.r + 1; rr <= m.e.r; rr++) noInheritRows.add(rr - off);
    }
  }
  let cur = null;
  let lastDate = null;
  const seen = new Map(); // 票号 -> 发票（迪奇/思信/EDU/银辉/MMI 每行都重填票号；同号归并同一票）

  rows.forEach((r, i) => {
    if (i <= hdrIdx || !r) return;
    if (opts.skipRow && opts.skipRow(r, cols)) return; // 投喂排期表的汇总行（如思信「X月份/合计HK$:」行）
    // 投喂路径：票号列空行仅在「票号列真合并单元格」内才归并上一票，其余整行跳过
    if (noInheritRows && !trim(cols.no != null ? r[cols.no] : '') && !noInheritRows.has(i)) return;
    const rowNo = i + 1;
    const ds = dateSerialOf(cols.date != null ? r[cols.date] : null);
    if (ds !== null) lastDate = ds;
    const no0 = trim(cols.no != null ? r[cols.no] : '');
    const no = no0 && opts.cleanNo ? opts.cleanNo(no0) : no0;
    const code = trim(cols.code != null ? r[cols.code] : '');
    const qty = numOrNull(cols.qty != null ? r[cols.qty] : null);
    let price = numOrNull(cols.price != null ? r[cols.price] : null);
    const amt = cols.amt != null ? numOrNull(r[cols.amt]) : null;
    // SHUSHUPAPA 排期表 示例编号 起数据右移一格：「单价」列填的是国家文本，真正单价在右一格（总金额列），
    // 数量/走货金额USD 列仍对齐。单价格是非空文本、右格是数字、且 数量×右格 ≈ 走货金额（兼容 70% 票）时按右格取
    if (sn === 'SHUSHUPAPA' && price === null && cols.price != null && trim(r[cols.price])) {
      const shifted = numOrNull(r[cols.price + 1]);
      const fit = (k) => shifted !== null && qty !== null && amt !== null && Math.abs(qty * shifted * k - amt) <= 1e-3 * Math.max(1, Math.abs(amt));
      if (fit(1) || fit(0.7)) {
        price = shifted;
        warnings.push({ type: 'shushuShift', sheet: sn, row: rowNo, invNo: no || (cur && cur.invNo), text: `SHUSHUPAPA ${no || (cur && cur.invNo)}：第${rowNo}行「单价」列填的是「${trim(r[cols.price])}」，该行数据右移了一格，已按右一列单价 ${shifted} 生成，请人工核对` });
      }
    }
    const discAmt = cols.discAmt != null ? numOrNull(r[cols.discAmt]) : null;
    const note = cols.note != null ? trim(r[cols.note]) : '';
    const hasContent = code !== '' || qty !== null || price !== null || (amt !== null && amt !== 0);
    if (no) {
      cur = seen.get(no);
      if (!cur) {
        cur = {
          invNo: no, customer: sn, variant: conf.variant, date: ds ?? lastDate, ym: ymOf(ds ?? lastDate),
          lines: [], contracts: new Set(), sheet: sn, row: rowNo,
        };
        seen.set(no, cur);
        invoices.push(cur);
      }
    }
    if (!cur) {
      if (hasContent)
        warnings.push({ type: 'orphanLine', sheet: sn, row: rowNo, text: `${sn} 第${rowNo}行：有内容但不在任何发票号块内（首张票之前），已跳过，请人工核对` });
      return;
    }
    if (!no && !hasContent) return; // 空行/全 0 占位（彩星 =L*H→0 残留行）
    if ((sn === '迪奇' || sn === 'buzz') && !cur.market) {
      const mk = marketOf(sn, r);
      if (mk) cur.market = mk;
    }
    if (cols.buyer != null && !cur.buyer) {
      const b = trim(r[cols.buyer]);
      if (b) cur.buyer = b;
    }
    if (hasContent) {
      const ln = { kind: 'goods', code: code || null, qty, price, amt, discAmt };
      for (const [key, ci] of Object.entries(identityCols)) {
        const value = ci >= 0 ? trim(r[ci]) : '';
        if (value) ln[key] = key === 'sourceReference' ? value.replace(/-\d+$/, '') : value;
      }
      // buzz：净价（验货报告列）与其右一列降价差额（无表头，按位置取）——WM 票拆行用
      if (cols.netPrice != null) {
        ln.net = numOrNull(r[cols.netPrice]);
        ln.diff = numOrNull(r[cols.netPrice + 1]);
      }
      // SHU SHU PAPA：备注"剩余70%发票"→ 票面单价×0.7（无样票，警告）；
      // 投喂排期表无备注列时按 金额≈数量×单价×0.7 反推（derivePct70）
      if (sn === 'SHUSHUPAPA' && /70\s*%/.test(note)) ln.pct70 = true;
      else if (sn === 'SHUSHUPAPA' && /30\s*%/.test(note) && /定金/.test(note)) ln.pct30 = true;
      else if (sn === 'SHUSHUPAPA' && opts.derivePct70 && amt !== null && qty && price
        && Math.abs(amt - qty * price * 0.7) <= 1e-3 * Math.max(1, Math.abs(amt))) ln.pct70 = true;
      cur.lines.push(ln);
    }
    const contract = cols.sn != null ? trim(r[cols.sn]) : '';
    if (contract) cur.contracts.add(contract);
  });

  // 无明细的票（只有票号行）
  for (const inv of invoices.filter((x) => x.lines.length === 0))
    warnings.push({ type: 'emptyInv', sheet: sn, row: inv.row, invNo: inv.invNo, text: `${sn} ${inv.invNo}：没有明细行，请人工核对` });
  return invoices;
}

/** 票数/月份/票型汇总（finalize 与 mergeHxgParsed 共用） */
/**
 * buzz WM 票（客名 WMU/WMC 等 WM 开头，104xxx 段）拆行变换：
 * 排期表/记录里「验货报告」列=净价（原价−降价差额），其右一列=降价差额，净价+差额=单价(K)。
 * 文员 WM 票口径（样票 示例编号）：净价、降价差额拆成同货号同数量两行，票面单价=来源价×0.967、
 * 金额=数量×单价×0.967（相对单价再乘一次 0.967）。净价+差额≠单价的行不拆、留原样并警告。
 * 非 WM 的 buzz 票不拆，仅清掉解析时带的 net/diff 临时字段。
 */
function transformBuzzWmLines(inv, warnings) {
  const isWm = /^wm/i.test(inv.buyer ?? '');
  const out = [];
  for (const l of inv.lines) {
    const { net, diff, ...rest } = l;
    if (!isWm || net === null || net === undefined || !diff) { out.push(rest); continue; }
    if (rest.price !== null && Math.abs(net + diff - rest.price) > 0.005) {
      warnings.push({ type: 'wmSplit', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `buzz ${inv.invNo}：${rest.code ?? ''} 净价 ${net} + 降价 ${diff} ≠ 单价 ${rest.price}，该行按原单价生成，请人工核对` });
      out.push(rest);
      continue;
    }
    const qty = rest.qty ?? 0;
    out.push({ ...rest, price: net, amt: net * qty, wm: true });
    // 第二行降价差额：discAmt 置 0（不是 null）避免折扣校验把它当无折后金额行重复计入
    out.push({ ...rest, price: diff, amt: diff * qty, discAmt: 0, wm: true });
  }
  inv.lines = out;
}
function hxgSummaryOf(invoices) {
  const customers = {};
  for (const inv of invoices) {
    const c = (customers[inv.customer] = customers[inv.customer] || { count: 0, months: {}, variants: {} });
    c.count++;
    const m = inv.ym || '日期缺失';
    c.months[m] = (c.months[m] || 0) + 1;
    const v = HXG_VARIANTS[inv.variant]?.label || inv.variant;
    c.variants[v] = (c.variants[v] || 0) + 1;
  }
  return customers;
}

/** 客户级后处理（合同号/思信变换/彩星反推/迪奇 Less/buzz 折扣校验/静态注意），
 *  parseHxgRecords 与 parseHxgFeed 共用；返回 summary.customers */
function finalizeHxgParsed(invoices, warnings) {
  for (const inv of invoices) {
    const list = [...inv.contracts];
    // 一票多合同号：S/N 只写第一行的合同号（银辉 示例编号 等），其余保留警告
    inv.contract = list.length ? list[0] : null;
    if (list.length > 1)
      warnings.push({ type: 'snMulti', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：一票对应 ${list.length} 个合同号（${list.join('、')}），S/N 只写第一个「${list[0]}」，请人工核对` });
    delete inv.contracts;
    // 记录原始总金额（未打折的记录合计），生成时写在表格右上方作红色核对参考
    inv.refTotal = inv.lines.reduce((s, l) => s + (l.amt ?? (l.qty ?? 0) * (l.price ?? 0)), 0);

    if (inv.customer === 'buzz' && !inv.extra) transformBuzzWmLines(inv, warnings);

    if (inv.customer === '思信' && !inv.extra) {
      inv.variant = /^SCL/i.test(inv.invNo) ? 'sxscl' : 'sxstd';
      transformSixinLines(inv, warnings);
    }
    // 彩星个别票记录缺原价单价（示例编号/71/73 只有折后单价/折后金额）：按 折后金额÷(数量×0.955) 反推原价
    if (inv.customer === '彩星' && !inv.extra) {
      let derived = false;
      for (const l of inv.lines) {
        if (l.price === null && l.qty && l.discAmt) {
          l.price = l.discAmt / (l.qty * 0.955);
          l.amt = l.qty * l.price;
          derived = true;
        }
      }
      if (derived)
        warnings.push({ type: 'cxDerived', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `彩星 ${inv.invNo}：记录缺原价单价，按 折后金额÷(数量×0.955) 反推原价生成（票面单价=×0.967，Less:0.5%+4%），请人工核对` });
    }
    if (inv.customer === '迪奇' && !inv.extra) detectDiqiLess(inv, warnings);
    // buzz 折扣规则（2026-10 文员）：美国标准票记录打 0.98 折扣，其他标准（加拿大/欧洲）不打折；
    // 票面仍按样票 示例编号 版式（金额=E*H*0.967），这里只校验记录比率与标准是否相符
    if (inv.customer === 'buzz' && inv.market) {
      const sumK = inv.lines.reduce((s, l) => s + (l.amt ?? 0), 0);
      const sumL = inv.lines.reduce((s, l) => s + (l.discAmt ?? l.amt ?? 0), 0);
      const ratio = sumK > 0 ? sumL / sumK : null;
      const expect = inv.market === '美国标准' ? 0.98 : 1;
      if (ratio !== null && Math.abs(ratio - expect) >= 0.0015)
        warnings.push({ type: 'buzzDisc', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `buzz ${inv.invNo}：${inv.market}票记录折扣比率 ${ratio.toFixed(4)} 与规则（美国标准 0.98 / 其他标准无折扣）不符，请人工核对` });
    }
    if (inv.customer === 'SHUSHUPAPA' && inv.lines.some((l) => l.pct70))
      warnings.push({ type: 'shushu70', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `SHUSHUPAPA ${inv.invNo}：备注「剩余70%发票」，票面单价按记录×0.7 生成（无样票），请人工核对` });
    if (inv.customer === 'SHUSHUPAPA' && inv.lines.some((l) => l.pct30))
      warnings.push({ type: 'shushu30', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `SHUSHUPAPA ${inv.invNo}：备注「先开30%定金发票」（走货金额列为 0），票面单价按 ×0.3 生成（无样票，与同 PO「剩余70%发票」票对称），请人工核对` });
    if (inv.lines.some((l) => l.kind !== 'note' && l.price === 0))
      warnings.push({ type: 'zeroPrice', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：含单价为 0 的明细，已保留源值；未仅凭 0 判为子行或改为 1，请核对其用途` });
    if (inv.lines.some((l) => (l.qty ?? 0) > 0 && (l.price === null || l.price === undefined)))
      warnings.push({ type: 'noPrice', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：源表无单价（数量有数但单价为空），票面单价/金额将按 0 生成，请人工补单价` });
    if (!inv.ym)
      warnings.push({ type: 'noDate', sheet: inv.sheet, row: inv.row, invNo: inv.invNo, text: `${inv.customer} ${inv.invNo}：发票日期缺失，表头日期留空` });
  }

  // 静态注意（每个客户一次）
  const once = (customer, text) => {
    if (invoices.some((i) => i.customer === customer)) warnings.push({ type: 'custNote', sheet: customer, text });
  };
  once('迪士尼', '迪士尼：历史样票货号与记录货号可能不一致（海关备案号需人工核对）；已按记录货号生成，请人工核对');
  once('buzz', '内置提示：buzz 模板自带样票（单行贴纸票版式），非你上传的数据，无需处理');
  once('MAXX', '国际簿仅有首期50%模款样票（SET 单位且不打折）；货款票按 PCS + 无首期 + 单价×0.967（2026-10-13 用户口径）生成，MAXX/银辉 请人工核对');
  once('银辉', '国际簿仅有首期50%模款样票（SET 单位且不打折）；货款票按 PCS + 无首期 + 单价×0.967（2026-10-13 用户口径）生成，MAXX/银辉 请人工核对');
  once('MMI', 'MMI：无文员样票，借用贸易簿 360 版式（单价×0.967，H=K*0.967 参照右侧原价列），请人工核对');
  once('SHUSHUPAPA', 'SHU SHU PAPA：无文员样票，借用贸易簿 360 版式（单价×0.967）；备注「剩余70%发票」的行按 单价×0.7×0.967 生成、备注「先开30%定金发票」的行按 单价×0.3×0.967 生成，请人工核对');
  once('EDU', 'EDU：原簿 EDU/EDU(其它款) 样票没有抬头单元格（原簿即如此），保持原样；货号按 首段/次段 拆 D/E 两列（样票 F12/BN328 推定），请人工核对');
  once('思信', '思信：SCL 票号用 Sheet1 版式、数字票号用施信准版式；施信准5% 变体在当前记录里找不到触发特征，未自动使用，如有 5%扣款票请人工改用对应空模板；其它款/模费票已从排期表「其它费用」sheet 自动生成（单独文件）');
  // 其他款/模具费（extra）口径说明（仅当该客有 extra 票时）
  const onceX = (customer, text) => {
    if (invoices.some((i) => i.customer === customer && i.extra)) warnings.push({ type: 'custNote', sheet: customer, text });
  };
  onceX('buzz', 'buzz 其他款/模具费：排期表「其他费」=其他款（单价×0.967，右侧镜像原价）、「模具手办费」=模具费（全额不打折），有打印纸版式单独文件输出，请人工核对');
  onceX('迪奇', '迪奇 其他款/模具费：Reference 列含「模费/手办费」→模具费（全额不打折），其余→其他款（×0.967 带原价镜像），有打印纸版式单独文件输出，请人工核对');
  onceX('思信', '思信 其他款/模具费：「其它费用」sheet「以下是2026年其它款」之前=模具费（按金额列开票，含 50% 分期行），之后=其他款（×0.967 带原价镜像），请人工核对');
  onceX('彩星', '彩星 其他款/模具费：说明列含「工模/手办」→模具费（按金额列开票，已是 40%/60% 分期额），其余→其他款（×0.967，无样票按香港组口径推定），请人工核对');
  onceX('迪士尼', '迪士尼 其它款全部按模具费生成（HKD 总金额列，全额不打折）；备注「华康C」行为华康厂区费用已跳过，请人工核对');
  onceX('360', '360 其他款/模款：按行后最近的小计标签行分类（「模具款及手办费用」=模款全额不打折、「其它款」=其他款 ×0.967 带原价镜像），贸易版式单独文件输出，请人工核对');
  onceX('MMI', 'MMI 其它费用全部按模款生成（贸易版式，USD，全额不打折），请人工核对');
  onceX('MAXX', 'MAXX 其它款全部按模具费生成（国际版式，USD；金额列已是首期/尾期分期额，单价=金额÷数量），请人工核对');
  onceX('银辉', '银辉 其它款全部按模具费生成（国际版式，HK$；按金额列开票，单价=金额÷数量）；样票与排期表明细可能不同，按排期表有效明细生成，请人工核对');
  if (invoices.some((i) => i.customer === 'buzz' && i.lines.some((l) => l.wm)))
    warnings.push({ type: 'custNote', sheet: 'buzz', text: 'buzz WM 票（客名 WMU/WMC）：单价取「验货报告」净价列（非「单价」列），票面单价=净价×0.967，降价差额拆成同货号同数量第二行，金额=数量×单价×0.967（既有文员口径），请人工核对' });

  return hxgSummaryOf(invoices);
}

/**
 * 解析《发票记录原件.xlsx》：11 个客户 sheet，表头在第 1 行，列位按表头名解析。
 * @returns { invoices, warnings, summary }
 */
export function parseHxgRecords(wb) {
  const invoices = [];
  const warnings = [];
  const unknownSheets = [];

  for (const sn of wb.SheetNames) {
    const conf = HXG_CUSTOMERS[sn];
    if (!conf) {
      unknownSheets.push(sn);
      warnings.push({ type: 'unknownSheet', sheet: sn, text: `sheet「${sn}」没有对应客户配置，已跳过` });
      continue;
    }
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1, defval: null, raw: true });
    invoices.push(...parseHxgSheetRows(sn, conf, rows, 0, warnings));
  }

  const customers = finalizeHxgParsed(invoices, warnings);
  return { invoices, warnings, summary: { customers, unknownSheets } };
}

/** 投喂排期表通用的汇总行过滤（仅投喂路径；记录原件已被文员清理，无此类行）：
 *  ①日期列是不可解析的非空字符串（MAXX「7月份」、360「360 8月」、银辉「银辉 7月」/
 *  「币种」「USD」统计块），或 ②任意单元格文本含「合计」或月小结标记
 *  （思信/EDU/迪士尼/SHUSHUPAPA/buzz/MMI 月度合计行——这些行的票号列常被占位的
 *  0 或合计数值（如 11.示例编号）顶格，不能因为有「票号」就放行）。
 *  月小结标记 = 带「份」的「3月份」，或带非数字前缀的「银辉 7月」「360 8月」；
 *  裸「7月」是 FA 列的月份标签（银辉/360 每行都有），不算。
 *  ③日期列是超出有效序列范围的数字（360 嵌入的「型号×月份」透视块把货号填在日期列）；
 *  ④数量/单价/货号全空但金额列有非零数（迪奇「出货打发票金额：」「其他2%金额：」等
 *  月度费用小计行）。 */
const feedSkipSummaryRow = (r, cols) => {
  const d = cols.date != null ? r[cols.date] : null;
  if (typeof d === 'string' && d.trim() && dateSerialOf(d) === null) return true;
  if (typeof d === 'number' && dateSerialOf(d) === null) return true;
  if (r.some((v) => {
    if (typeof v !== 'string') return false;
    const s = v.trim();
    if (/合计/.test(s)) return true;
    if (/\d{1,2}\s*月份/.test(s)) return true;
    if (/\D\d{1,2}\s*月(?!\d)/.test(s) && !/^\d{4}/.test(s)) return true;
    return false;
  })) return true;
  const qtyNull = numOrNull(cols.qty != null ? r[cols.qty] : null) === null;
  const priceNull = numOrNull(cols.price != null ? r[cols.price] : null) === null;
  const codeEmpty = trim(cols.code != null ? r[cols.code] : '') === '';
  const amt = numOrNull(cols.amt != null ? r[cols.amt] : null);
  return qtyNull && priceNull && codeEmpty && amt !== null && amt !== 0;
};

/**
 * 排期表投喂配置（文件名关键词优先——sheet 名有冲突：已出发票=MAXX/SHUSHUPAPA/EDU、
 * 出货发票=buzz/MMI/思信、已打印发票=360/迪士尼；HXG_FEED_SHEET_FALLBACK 只兜底无歧义签名）。
 * cols：对 HXG_CUSTOMERS[customer].cols 的覆盖（null = 排期表没有该列，跳过）；
 * cleanNo：票号清洗；skipRow：汇总行过滤（缺省 feedSkipSummaryRow）；
 * derivePct70：SHUSHUPAPA 70% 行按金额比率反推（备注列直读「剩余70%发票」/「先开30%定金发票」，
 * 比率反推兜底备注为空的情况）。
 */
export const HXG_FEEDS = [
  { re: /dickie|迪奇/i, customer: '迪奇', sheet: '已出发票（HK抬头）' },
  { re: /buzz/i, customer: 'buzz', sheet: '出货发票' },
  { re: /shushupapa/i, customer: 'SHUSHUPAPA', sheet: '已出发票', derivePct70: true },
  { re: /maxx/i, customer: 'MAXX', sheet: '已出发票', cleanNo: (s) => s.split('\n')[0].replace(/[（(].*$/, '').trim() },
  { re: /银辉/i, customer: '银辉', sheet: '发票已出票' },
  { re: /edu/i, customer: 'EDU', sheet: '已出发票' },
  { re: /mmi/i, customer: 'MMI', sheet: '出货发票' },
  { re: /seasons|施信|思信/i, customer: '思信', sheet: '出货发票' },
  { re: /360/, customer: '360', sheet: '已打印发票' },
  { re: /彩星/i, customer: '彩星', sheet: '2026年出货发票' },
  { re: /迪士尼|disney/i, customer: '迪士尼', sheet: '已打印发票' },
];

/** sheet 签名兜底（仅无歧义的；文件名不含关键词时用它识别） */
export const HXG_FEED_SHEET_FALLBACK = {
  '已出发票（HK抬头）': '迪奇',
  '发票已出票': '银辉',
  '2026年出货发票': '彩星',
};

/**
 * 解析单个客户排期表原件（投喂路径）：先按文件名关键词识别客户（HXG_FEEDS），
 * 识别不了再用无歧义 sheet 签名兜底（HXG_FEED_SHEET_FALLBACK）。在目标 sheet 前 10 行里
 * 找表头行（归一化后含「发票号」或为「INVOICE」的行），用该客户的 HXG_CUSTOMERS.cols
 * （可被 HXG_FEEDS.cols 覆盖）按表头名解析列位，行解析/归并/后处理与 parseHxgRecords
 * 完全同路径。排期表是全年数据，票量比发票记录原件多属正常，前端按月份筛选。
 * 识别不了时返回 customer: null。
 * @returns { customer, sheet, invoices, warnings, summary }
 */
export function parseHxgFeed(fileName, wb) {
  const warnings = [];
  const empty = { customers: {}, unknownSheets: [] };
  let feed = HXG_FEEDS.find((f) => f.re.test(fileName)) || null;
  let sheetName = null;
  if (feed) {
    if (!wb.SheetNames.includes(feed.sheet)) {
      warnings.push({ type: 'feedNoSheet', text: `文件「${fileName}」按文件名识别为 ${feed.customer} 排期表，但找不到 sheet「${feed.sheet}」（现有：${wb.SheetNames.join(' / ')}），已跳过` });
      return { customer: feed.customer, sheet: null, invoices: [], warnings, summary: empty };
    }
    sheetName = feed.sheet;
  } else {
    for (const sn of wb.SheetNames) {
      if (HXG_FEED_SHEET_FALLBACK[sn]) {
        feed = HXG_FEEDS.find((f) => f.customer === HXG_FEED_SHEET_FALLBACK[sn]);
        sheetName = sn;
        break;
      }
    }
  }
  if (!feed) {
    warnings.push({ type: 'unknownFeed', text: `文件「${fileName}」无法识别是哪个客户的排期表（文件名不含客户关键词，也无特征 sheet），已跳过` });
    return { customer: null, sheet: null, invoices: [], warnings, summary: empty };
  }
  const customer = feed.customer;
  const rows = XLSX.utils.sheet_to_json(wb.Sheets[sheetName], { header: 1, defval: null, raw: true });
  let hdrIdx = -1;
  for (let i = 0; i < Math.min(10, rows.length); i++) {
    if ((rows[i] || []).some((c) => { const h = normHdr(c); return h.includes('发票号') || /^INVOICE$/i.test(h); })) { hdrIdx = i; break; }
  }
  if (hdrIdx < 0) {
    warnings.push({ type: 'feedNoHeader', sheet: sheetName, text: `文件「${fileName}」的 sheet「${sheetName}」前 10 行找不到表头行（含「发票号」/「INVOICE」的行），已跳过` });
    return { customer, sheet: sheetName, invoices: [], warnings, summary: empty };
  }
  warnings.push({ type: 'feedNote', sheet: sheetName, text: `文件「${fileName}」识别为 ${customer} 排期表（sheet「${sheetName}」，表头第 ${hdrIdx + 1} 行），按排期表数据生成` });
  const conf = feed.cols ? { ...HXG_CUSTOMERS[customer], cols: { ...HXG_CUSTOMERS[customer].cols, ...feed.cols } } : HXG_CUSTOMERS[customer];
  const ws = wb.Sheets[sheetName];
  const rowOffset = ws['!ref'] ? XLSX.utils.decode_range(ws['!ref']).s.r : 0;
  const invoices = parseHxgSheetRows(customer, conf, rows, hdrIdx, warnings, {
    cleanNo: feed.cleanNo, skipRow: feed.skipRow ?? feedSkipSummaryRow, derivePct70: feed.derivePct70,
    noColMerges: ws['!merges'] || [], rowOffset,
  });
  for (const inv of invoices) inv.feedFile = fileName;
  // 其他款/模具费 sheet（与该客户货款 sheet 同簿）：解析结果塞进同一 invoices 数组，
  // mergeHxgParsed 去重、月份筛选、summary 自动生效；生成时按 inv.extra 分流到第二个文件
  const xparser = HXG_EXTRA_PARSERS[customer];
  if (xparser) invoices.push(...xparser(wb, warnings));
  const customers = finalizeHxgParsed(invoices, warnings);
  return { customer, sheet: sheetName, invoices, warnings, summary: { customers, unknownSheets: [] } };
}

/* ================= 其他款/模具费（extra）解析 =================
 * 数据源：各客排期表里的「其它款/其他费/模具手办费」类 sheet（与货款 sheet 同簿，仅投喂路径）。
 * 分类口径（2026-10-20 逐 sheet 考证 + 样票比对）：
 *  - 其他款：票面单价=原价×0.967（pp/trade 带原价镜像列；国际簿无样票按同口径定值）；
 *  - 模具费：全额不打折，按金额列开票（数量缺省 1，单价=金额/数量）。
 * 产出的发票对象带 extra: true / extraKind: 'other'|'mold' / currency（行级 ln.cur 同值），
 * variant 按客户格式组（HXG_EXTRA_FORMAT）定。 */

/** sheet 名容错查找（EDU「其它款项 」带尾空格） */
function findExtraSheetName(wb, name) {
  if (wb.SheetNames.includes(name)) return name;
  return wb.SheetNames.find((s) => s.trim() === name.trim()) || null;
}

/** 表头行定位：前 maxScan 行内含「发票号」/「发票NO」/INVOICE 的行；找不到返回 -1
 *  （不能只看「发票」：银辉 R4「工模发票」、MAXX R3「发票抬头：…」会误判） */
function extraHdrRow(rows, maxScan = 10) {
  for (let i = 0; i < Math.min(maxScan, rows.length); i++) {
    if ((rows[i] || []).some((c) => {
      const h = normHdr(c);
      return h.includes('发票号') || /发票\s*NO/i.test(h) || /^INVOICE/i.test(h);
    })) return i;
  }
  return -1;
}

/** 真合并单元格向下填充（彩星/MAXX 其它款：票号/日期列多行合并，续行继承锚点值）。
 *  直接改 rows（解析前的一次性预处理）；cols 为 0-based 列号，rowOffset 为 !ref 起始行。 */
function extraMergeFillDown(rows, merges, cols, rowOffset) {
  for (const m of merges || []) {
    if (m.e.r <= m.s.r) continue;
    for (const ci of cols) {
      if (ci < m.s.c || ci > m.e.c) continue;
      const anchor = rows[m.s.r - rowOffset]?.[ci];
      if (anchor === null || anchor === undefined || anchor === '') continue;
      for (let rr = m.s.r + 1; rr <= m.e.r; rr++) {
        const row = rows[rr - rowOffset];
        if (!row) continue;
        if (row[ci] === null || row[ci] === undefined || row[ci] === '') row[ci] = anchor;
      }
    }
  }
}

/** extra 行 → 发票归并（每行须自带票号，同票号归并同一票；彩星/MAXX 的续行靠
 *  extraMergeFillDown 真合并预填票号。无票号有内容行=未打票/杂项，计数警告后跳过——
 *  不按位置归并上一票：思信等 sheet 票号后紧跟大量未打票杂行） */
function extraCollect(customer, sheetLabel, rows, hdrIdx, colNo, colDate, lineOf, skipRow, warnings) {
  const invoices = [];
  const seen = new Map();
  let lastDate = null;
  let skipNoNo = 0;
  rows.forEach((r, i) => {
    if (i <= hdrIdx || !r) return;
    if (skipRow && skipRow(r)) return;
    const rowNo = i + 1;
    const ds = dateSerialOf(colDate != null ? r[colDate] : null);
    if (ds !== null) lastDate = ds;
    const no0 = trim(colNo != null ? r[colNo] : '');
    // 票号列里是长文本/多行说明的（迪奇杂项备注行）不是票号，整行当杂项跳过
    const no = no0.length > 20 || /\n/.test(no0) ? '' : no0;
    const ln = lineOf(r, rowNo);
    if (!no) {
      if (ln) skipNoNo++;
      return;
    }
    let cur = seen.get(no);
    if (!cur) {
      const fmt = HXG_EXTRA_FORMAT[customer];
      cur = {
        invNo: no, customer, variant: HXG_EXTRA_VARIANT[fmt][ln ? ln.kind : 'other'],
        date: ds ?? lastDate, ym: ymOf(ds ?? lastDate),
        lines: [], contracts: new Set(), sheet: sheetLabel, row: rowNo,
        extra: true, extraKind: ln ? ln.kind : 'other', currency: ln ? ln.cur : 'HK$',
      };
      seen.set(no, cur);
      invoices.push(cur);
    }
    if (!ln) return; // 票号行本身无内容（占位）
    // 同一票内行分类必须一致（如 360 模款段与其它款段同号不会混；不一致以首行为准并警告）
    if (ln.kind !== cur.extraKind) {
      warnings.push({ type: 'extraKindMix', sheet: sheetLabel, row: rowNo, invNo: cur.invNo, text: `${customer} ${cur.invNo}：第${rowNo}行分类（${ln.kind === 'mold' ? '模具费' : '其他款'}）与票首行（${cur.extraKind === 'mold' ? '模具费' : '其他款'}）不一致，已按票首行归并，请人工核对` });
      return;
    }
    // 仅独立费用且有非零金额依据时补数量 1；零额说明/子行不制造数量或费用。
    if (ln.qty === null || ln.qty === undefined || ln.qty === 0) {
      if (Number.isFinite(ln.amt) && ln.amt !== 0) {
        warnings.push({ type: 'qty0As1', sheet: sheetLabel, row: rowNo, invNo: cur.invNo, text: `${customer} ${cur.invNo}：第${rowNo}行${ln.code ? `「${ln.code}」` : ''}数量为空或 0，有独立费用金额 ${ln.amt}，已按数量 1、单价=金额开票，请人工核对` });
        cur.lines.push({ kind: 'goods', code: ln.code ?? null, qty: 1, price: ln.amt, amt: ln.amt, cur: ln.cur });
      } else {
        warnings.push({ type: 'extraZeroNote', sheet: sheetLabel, row: rowNo, invNo: cur.invNo, text: `${customer} ${cur.invNo}：第${rowNo}行${ln.code ? `「${ln.code}」` : ''}数量为空或 0，且无非零金额依据，已保留为说明行，不补数量或费用，请核对是否为子行` });
        cur.lines.push({ kind: 'note', code: ln.code ?? null, qty: null, price: null, amt: 0, cur: ln.cur });
      }
      return;
    }
    cur.lines.push({ kind: 'goods', code: ln.code ?? null, qty: ln.qty, price: ln.price, amt: ln.amt ?? ln.qty * (ln.price ?? 0), cur: ln.cur });
  });
  if (skipNoNo)
    warnings.push({ type: 'extraNoNo', sheet: sheetLabel, text: `${customer} ${sheetLabel}：${skipNoNo} 行有内容但没有发票号（未打票/杂项），已跳过` });
  // 有票号但整票缺金额/单价
  for (const inv of invoices) {
    if (!inv.lines.length)
      warnings.push({ type: 'extraNoAmt', sheet: sheetLabel, row: inv.row, invNo: inv.invNo, text: `${customer} ${inv.invNo}：只有票号没有有效金额行，未生成，请人工核对` });
  }
  return invoices.filter((inv) => inv.lines.length);
}

/** 通用汇总/合计行过滤（extra 版：列位各异，直接扫全行文本） */
const extraSkipSummary = (r) => r.some((v) => {
  if (typeof v !== 'string') return false;
  const s = v.trim();
  if (!s) return false;
  if (/合计|取消发票/.test(s)) return true;
  if (/\d{1,2}\s*月份/.test(s)) return true;
  if (/^以下是/.test(s)) return true;
  return false;
});

/** extra 通用解析骨架：定位 sheet/表头 → extraCollect */
function parseExtraSheet(wb, customer, sheetName, colNo, colDate, lineOf, { skipRow = extraSkipSummary, mergesFill = null } = {}, warnings = []) {
  const sn = findExtraSheetName(wb, sheetName);
  if (!sn) return [];
  const ws = wb.Sheets[sn];
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, raw: true });
  const rowOffset = ws['!ref'] ? XLSX.utils.decode_range(ws['!ref']).s.r : 0;
  if (mergesFill) extraMergeFillDown(rows, ws['!merges'] || [], mergesFill, rowOffset);
  const hdrIdx = extraHdrRow(rows);
  if (hdrIdx < 0) return [];
  return extraCollect(customer, sn, rows, hdrIdx, colNo, colDate, lineOf, skipRow, warnings);
}

/** buzz：其他费 sheet=其他款、模具手办费 sheet=模费（同布局）。列：B日期 C Reference D费用描述
 *  E產品編號 F產品名称 G數量 I单价 K金额HK$ L发票号。其他款样票 示例编号（I=原价，×0.967）。 */
function parseBuzzExtra(wb, warnings = []) {
  const lineOf = (kind) => (r) => {
    const desc = trim(r[3]) || trim(r[4]);
    const qty = numOrNull(r[6]);
    const price = numOrNull(r[8]);
    const amt = numOrNull(r[10]);
    if (!desc && qty === null && price === null && (amt === null || amt === 0)) return null;
    if (amt === 0 && price === null && !desc) return null; // 无说明的 K=0 占位行
    if (kind === 'mold') {
      const q = qty === null || qty === 0 ? 1 : qty;
      const total = amt ?? (qty !== null && price !== null ? qty * price : null);
      if (total === null) return null;
      return { kind, code: desc || null, qty, price: total / q, amt: total, cur: 'HK$' };
    }
    return { kind, code: desc || null, qty, price, amt: qty !== null && qty !== 0 && price !== null ? qty * price : amt, cur: 'HK$' };
  };
  return [
    ...parseExtraSheet(wb, 'buzz', '其他费', 11, 1, lineOf('other'), {}, warnings),
    ...parseExtraSheet(wb, 'buzz', '模具手办费', 11, 1, lineOf('mold'), {}, warnings),
  ];
}

/** 迪奇：其他款项 sheet。列：B日期 C Reference(费用类型) D PO.NO(模费描述) F產品編號 G產品名称
 *  H數量 J单价 K金额HK$ M发票号NO.。C 含「模费/手办费」→模费（desc=D），否则→其他款（desc=F 货号，
 *  J=原价 ×0.967，样票 示例编号 J=原价×折扣）。 */
function parseDiqiExtra(wb, warnings = []) {
  return parseExtraSheet(wb, '迪奇', '其他款项', 12, 1, (r) => {
    const feeType = trim(r[2]);
    const qty = numOrNull(r[7]);
    const price = numOrNull(r[9]);
    const amt = numOrNull(r[10]);
    if (!feeType && !trim(r[3]) && !trim(r[5]) && qty === null && price === null && amt === null) return null;
    if (/模费|手办费/.test(feeType)) {
      const q = qty === null || qty === 0 ? 1 : qty;
      const total = amt ?? (qty !== null && price !== null ? qty * price : null);
      if (total === null) return null;
      return { kind: 'mold', code: trim(r[3]) || feeType, qty, price: total / q, amt: total, cur: 'HK$' };
    }
    return { kind: 'other', code: trim(r[5]) || trim(r[3]) || null, qty, price, amt: qty !== null && qty !== 0 && price !== null ? qty * price : amt, cur: 'HK$' };
  }, {}, warnings);
}

/** 思信：其它费用 sheet。列：A日期 D PO.NO F產品編號 G產品名称 H数量 I单价 J金额HK$ K发票号 L备注。
 *  B 列「以下是2026年其它款」分界：前=模费（按 J 金额开票，含 50% 分期行），后=其他款
 *  （I=原价 ×0.967，样票 示例编号；J 是 55% 收款额不用）。 */
function parseSixinExtra(wb, warnings = []) {
  const sn = findExtraSheetName(wb, '其它费用');
  if (!sn) return [];
  const ws = wb.Sheets[sn];
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, raw: true });
  const hdrIdx = extraHdrRow(rows);
  if (hdrIdx < 0) return [];
  let boundary = rows.length;
  rows.forEach((r, i) => {
    if (i > hdrIdx && /^以下是/.test(trim(r?.[1] ?? ''))) boundary = Math.min(boundary, i);
  });
  return extraCollect('思信', sn, rows, hdrIdx, 10, 0, (r, rowNo) => {
    const code = trim(r[5]);
    const qty = numOrNull(r[7]);
    const price = numOrNull(r[8]);
    const amt = numOrNull(r[9]);
    if (!code && !trim(r[3]) && qty === null && price === null && amt === null) return null;
    if (rowNo - 1 < boundary) { // 分界前=模费
      const q = qty === null || qty === 0 ? 1 : qty;
      const total = amt ?? (qty !== null && price !== null ? qty * price : null);
      if (total === null) return null;
      return { kind: 'mold', code: code || trim(r[3]) || null, qty, price: total / q, amt: total, cur: 'HK$' };
    }
    return { kind: 'other', code: code || trim(r[3]) || null, qty, price, amt: qty !== null && qty !== 0 && price !== null ? qty * price : amt, cur: 'HK$' };
  }, (r) => extraSkipSummary(r), warnings);
}

/** 彩星：2026其他费用 sheet。列：A日期 B说明 D PO.NO F產品編號 G產品名称 H数量 I单价
 *  J金额HK$ K发票号 L备注。B 含「工模/手办」→模费（按 J 开票，J 已是 40%/60% 分期额），
 *  否则→其他款（I=原价 ×0.967，无样票按香港组口径推定）。K/A 列真合并单元格续行继承。 */
function parseCaixingExtra(wb, warnings = []) {
  return parseExtraSheet(wb, '彩星', '2026其他费用', 10, 0, (r) => {
    const note2 = trim(r[1]);
    const code = trim(r[5]);
    const qty = numOrNull(r[7]);
    const price = numOrNull(r[8]);
    const amt = numOrNull(r[9]);
    if (!note2 && !code && !trim(r[3]) && qty === null && price === null && amt === null) return null;
    if (/工模|手办/.test(note2)) {
      const q = qty === null || qty === 0 ? 1 : qty;
      const total = amt ?? (qty !== null && price !== null ? qty * price : null);
      if (total === null) return null;
      return { kind: 'mold', code: code || note2 || null, qty, price: total / q, amt: total, cur: 'HK$' };
    }
    return { kind: 'other', code: code || trim(r[3]) || note2 || null, qty, price, amt: qty !== null && qty !== 0 && price !== null ? qty * price : amt, cur: 'HK$' };
  }, { mergesFill: [0, 1, 3, 10] }, warnings); // A日期/B说明/D PO.NO/K发票号 都是真合并单元格
}

/** 迪士尼：其它款 sheet 全部=模费（香港组打印纸，HKD 用 I 列总金额，单价=I/数量）。
 *  列：A出票日期 C货号 D名称(产品) E名称(费用名) F数量 G总单价USD H总金额USD I总金额HKD J发票号 O备注。
 *  O 含「华康C」的行是别的厂区 → 跳过并警告。「其他费用」sheet（保险年费/贴纸费）无有效票号 → 只警告。 */
function parseDisneyExtra(wb, warnings) {
  const out = parseExtraSheet(wb, '迪士尼', '其它款', 9, 0, (r) => {
    const code = trim(r[2]);
    const fee = trim(r[4]);
    const qty = numOrNull(r[5]);
    const amtHKD = numOrNull(r[8]);
    if (!code && !fee && qty === null && amtHKD === null) return null;
    const q = qty === null || qty === 0 ? 1 : qty;
    if (amtHKD === null) return null;
    return { kind: 'mold', code: code || fee || null, qty, price: amtHKD / q, amt: amtHKD, cur: 'HK$' };
    // 华康C 厂区行整行跳过（下面统一警告），不进入归并
  }, { skipRow: (r) => extraSkipSummary(r) || /华康/i.test(trim(r[14] ?? '')) }, warnings);
  // 华康C 行统计警告
  const sn = findExtraSheetName(wb, '其它款');
  if (sn) {
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1, defval: null, raw: true });
    const hk = rows.filter((r) => r && /华康/i.test(trim(r[14] ?? '')) && trim(r[9] ?? '')).length;
    if (hk) warnings.push({ type: 'extraSkipFactory', sheet: sn, text: `迪士尼 其它款：${hk} 行备注为「华康C」（华康厂区费用），已跳过不生成华兴票` });
  }
  const sn2 = findExtraSheetName(wb, '其他费用');
  if (sn2) {
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[sn2], { header: 1, defval: null, raw: true });
    const n = rows.filter((r) => r && r.some((v) => v !== null && v !== '')).length;
    if (n > 2) warnings.push({ type: 'extraNoNo', sheet: sn2, text: `迪士尼 sheet「${sn2}」（保险年费/贴纸费等）没有有效发票号列，无法生成发票，请文员手工开票` });
  }
  return out;
}

/** 360：其它款 sheet。列：A出票日期 B Customer PO C release D PO release no. E货号 F名称(长文本)
 *  G数量 H总单价USD I总金额USD J总金额HKD K发票NO.。分类取该行之后最近的带标签小计行
 *  （F 含「模具款及手办费用」→模款，含「其它款」→其他款）；「取消发票」段整段跳过+警告。
 *  其他款 H=原价 ×0.967（贸易版式 K 列镜像，样票 示例编号）；模款按 H 单价（样票 示例编号 数量×单价）。USD。 */
function parse360Extra(wb, warnings) {
  const sn = findExtraSheetName(wb, '其它款');
  if (!sn) return [];
  const ws = wb.Sheets[sn];
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, raw: true });
  const hdrIdx = extraHdrRow(rows);
  if (hdrIdx < 0) return [];
  // 标签行（F 列）与取消段定位
  const labels = []; // { i, kind }
  let cancelAt = rows.length;
  rows.forEach((r, i) => {
    if (i <= hdrIdx || !r) return;
    if (r.some((v) => typeof v === 'string' && /取消发票/.test(v))) cancelAt = Math.min(cancelAt, i);
    const f = trim(r[5] ?? '');
    if (/模具款及手办费用/.test(f)) labels.push({ i, kind: 'mold' });
    else if (/其它款/.test(f)) labels.push({ i, kind: 'other' });
  });
  if (cancelAt < rows.length)
    warnings.push({ type: 'extraCancel', sheet: sn, text: `360 其它款：第${cancelAt + 1}行起为「取消发票」段，整段已跳过不生成` });
  const kindOf = (i) => {
    const below = labels.filter((l) => l.i > i);
    return below.length ? below[0].kind : null;
  };
  return extraCollect('360', sn, rows.slice(0, cancelAt), hdrIdx, 10, 0, (r, rowNo) => {
    const code = trim(r[4]);
    const name = trim(r[5]);
    const qty = numOrNull(r[6]);
    const price = numOrNull(r[7]);
    const amt = numOrNull(r[8]);
    if (!code && !name && qty === null && price === null && amt === null) return null;
    const kind = kindOf(rowNo - 1);
    if (!kind) return null; // 无法分类（标签行自身等）
    if (kind === 'mold') {
      const q = qty === null || qty === 0 ? 1 : qty;
      const p = price ?? (amt !== null ? amt / q : null);
      if (p === null) return null;
      return { kind, code: code || name || null, qty, price: p, amt: amt ?? (qty !== null && qty !== 0 ? qty * p : null), cur: 'USD' };
    }
    return { kind, code: code || name || null, qty, price, amt: amt ?? (qty !== null && price !== null ? qty * price : null), cur: 'USD' };
  }, (r) => extraSkipSummary(r), warnings);
}

/** MMI：其它费用 sheet 全部=模款（贸易，USD）。列：A日期 F產品名称(费用名) G数量 H单价 I金额US$ J发票号。 */
function parseMmiExtra(wb, warnings = []) {
  return parseExtraSheet(wb, 'MMI', '其它费用', 9, 0, (r) => {
    const name = trim(r[5]);
    const qty = numOrNull(r[6]);
    const price = numOrNull(r[7]);
    const amt = numOrNull(r[8]);
    if (!name && qty === null && price === null && amt === null) return null;
    const q = qty === null || qty === 0 ? 1 : qty;
    const p = price ?? (amt !== null ? amt / q : null);
    if (p === null) return null;
    return { kind: 'mold', code: name || null, qty, price: p, amt: amt ?? (qty !== null && qty !== 0 ? qty * p : null), cur: 'USD' };
  }, {}, warnings);
}

/** MAXX：其它款 sheet 全部=模费（国际，USD）。列：A出票日期 D货号 E名称 F数量 G单价USD
 *  H金额USD I发票NO. J备注。H 已是分期后金额（示例编号 首期50%）→ 单价=H/数量。I/A 列真合并续行继承。 */
function parseMaxxExtra(wb, warnings = []) {
  return parseExtraSheet(wb, 'MAXX', '其它款', 8, 0, (r) => {
    const code = trim(r[3]);
    const name = trim(r[4]);
    const qty = numOrNull(r[5]);
    const amt = numOrNull(r[7]);
    if (!code && !name && qty === null && amt === null) return null;
    const q = qty === null || qty === 0 ? 1 : qty;
    if (amt === null) return null;
    return { kind: 'mold', code: code || name || null, qty, price: amt / q, amt, cur: 'USD' };
  }, {
    mergesFill: [0, 8],
    skipRow: (r) => extraSkipSummary(r) || r.some((v) => typeof v === 'string' && /DN|收款/.test(v)),
  }, warnings);
}

/** 银辉：其它款 sheet（国际，HKD）。列：A出票日期 D货号 E名称 F数量 G总单价HKD H总金额HKD
 *  J首期/尾期标记 L发票NO.。分类同 360 用后续小计行（E 含「模具款及手办费用」→模费，E 含「其它款」
 *  →其他款）。按 H 金额开票（单价=H/数量）。 */
function parseYinhuiExtra(wb, warnings = []) {
  const sn = findExtraSheetName(wb, '其它款');
  if (!sn) return [];
  const ws = wb.Sheets[sn];
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, raw: true });
  const hdrIdx = extraHdrRow(rows);
  if (hdrIdx < 0) return [];
  const labels = [];
  rows.forEach((r, i) => {
    if (i <= hdrIdx || !r) return;
    const e = trim(r[4] ?? '');
    if (/模具款及手办费用/.test(e)) labels.push({ i, kind: 'mold' });
    else if (/其它款/.test(e)) labels.push({ i, kind: 'other' });
  });
  const kindOf = (i) => {
    const below = labels.filter((l) => l.i > i);
    return below.length ? below[0].kind : 'mold'; // 无后续标签按模费（当前数据全为模费）
  };
  return extraCollect('银辉', sn, rows, hdrIdx, 11, 0, (r, rowNo) => {
    const code = trim(r[3]);
    const name = trim(r[4]);
    const qty = numOrNull(r[5]);
    const amt = numOrNull(r[7]);
    if (!code && !name && qty === null && amt === null) return null;
    const kind = kindOf(rowNo - 1);
    const q = qty === null || qty === 0 ? 1 : qty;
    if (kind === 'mold') {
      if (amt === null) return null;
      return { kind, code: code || name || null, qty, price: amt / q, amt, cur: 'HK$' };
    }
    const price = numOrNull(r[6]);
    return { kind, code: code || name || null, qty, price, amt: amt ?? (qty !== null && price !== null ? qty * price : null), cur: 'HK$' };
  }, (r) => extraSkipSummary(r), warnings);
}

/** EDU：其它款项 sheet 没有发票号列（B日期 D货号 E款項名稱 F金額HKD）→ 无法生成，只警告 */
function parseEduExtra(wb, warnings) {
  const sn = findExtraSheetName(wb, '其它款项');
  if (!sn) return [];
  const rows = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1, defval: null, raw: true });
  const n = rows.filter((r, i) => i > 4 && r && r.some((v) => v !== null && v !== '')).length;
  if (n) warnings.push({ type: 'extraNoNo', sheet: sn, text: `EDU sheet「${sn}」（${n} 行款项）没有发票号列，无法生成其他款/模费票，请文员手工开票` });
  return [];
}

/** SHUSHUPAPA：其它款 sheet（同 MAXX 布局，贸易 USD）。当前数据全空（合计 0）。 */
function parseShushuExtra(wb, warnings = []) {
  return parseExtraSheet(wb, 'SHUSHUPAPA', '其它款', 8, 0, (r) => {
    const code = trim(r[3]);
    const name = trim(r[4]);
    const qty = numOrNull(r[5]);
    const amt = numOrNull(r[7]);
    if (!code && !name && qty === null && amt === null) return null;
    const q = qty === null || qty === 0 ? 1 : qty;
    if (amt === null) return null;
    return { kind: 'mold', code: code || name || null, qty, price: amt / q, amt, cur: 'USD' };
  }, { mergesFill: [0, 8] }, warnings);
}

/** 客户 → extra 解析器（parseHxgFeed 在货款 sheet 解析完后调用） */
export const HXG_EXTRA_PARSERS = {
  'buzz': parseBuzzExtra,
  '迪奇': parseDiqiExtra,
  '思信': parseSixinExtra,
  '彩星': parseCaixingExtra,
  '迪士尼': parseDisneyExtra,
  '360': parse360Extra,
  'MMI': parseMmiExtra,
  'MAXX': parseMaxxExtra,
  '银辉': parseYinhuiExtra,
  'EDU': parseEduExtra,
  'SHUSHUPAPA': parseShushuExtra,
};

/** XLSX.read 抛错时判断是否加密文件；是则返回提示警告对象，否则返回 null */
export function hxgEncryptedWarning(fileName, err) {
  const msg = String((err && err.message) || err || '');
  if (/password|encryption/i.test(msg))
    return { type: 'encrypted', text: `文件「${fileName}」已加密（密码保护），系统无法读取，请文员另存为无密码副本后再上传` };
  return null;
}

/** 单票字段级差异描述（a 在前 / b 在后），无差异返回空数组 */
function diffHxgInvoice(a, b) {
  const diffs = [];
  if (a.date !== b.date) diffs.push(`日期 ${a.date} ↔ ${b.date}`);
  if ((a.market ?? null) !== (b.market ?? null)) diffs.push(`国家/标准 ${a.market ?? '空'} ↔ ${b.market ?? '空'}`);
  if ((a.contract ?? null) !== (b.contract ?? null)) diffs.push(`合同号 ${a.contract ?? '空'} ↔ ${b.contract ?? '空'}`);
  if (a.lines.length !== b.lines.length) diffs.push(`行数 ${a.lines.length} ↔ ${b.lines.length}`);
  for (let i = 0; i < Math.min(a.lines.length, b.lines.length); i++) {
    const la = a.lines[i];
    const lb = b.lines[i];
    for (const [k, label] of [['code', '货号'], ['qty', '数量'], ['price', '单价'], ['amt', '金额'], ['discAmt', '折后金额']]) {
      const va = la[k] ?? null;
      const vb = lb[k] ?? null;
      const eq = typeof va === 'number' && typeof vb === 'number' ? Math.abs(va - vb) < 1e-9 : va === vb;
      if (!eq) diffs.push(`行${i + 1} ${label} ${va} ↔ ${vb}`);
    }
  }
  return diffs;
}

/**
 * 合并多个上传文件的解析结果（混合投喂：多个排期表 + 发票记录原件合订本）。
 * 同一 客户+票号 出现在多个来源时：内容一致 → 只保留一份；不一致 → feedDiff 警告，
 * 以排期表（feedFile 非空）为准。warnings 按文本去重（静态注意跨文件不重复）。
 */
export function mergeHxgParsed(parts) {
  const invoices = [];
  const warnings = [];
  const byKey = new Map();
  let dup = 0;
  for (const part of parts) {
    for (const inv of part.invoices || []) {
      // extra（其他款/模费）票与货款票号段相同但是不同的票（如思信 示例编号 模费票），键里带 extra 标记
      const key = `${inv.customer}|${inv.extra ? `x${inv.extraKind}` : 'goods'}|${inv.invNo}`;
      const prev = byKey.get(key);
      if (!prev) { byKey.set(key, inv); invoices.push(inv); continue; }
      const recSide = prev.feedFile && !inv.feedFile ? inv : prev;
      const feedSide = prev.feedFile && !inv.feedFile ? prev : inv;
      const diffs = diffHxgInvoice(recSide, feedSide);
      if (diffs.length) {
        warnings.push({
          type: 'feedDiff', sheet: inv.customer, invNo: inv.invNo,
          text: `${inv.customer} ${inv.invNo}：发票记录原件与排期表不一致（${diffs.join('；')}，前者=记录/后者=排期表），已按排期表数据生成，请人工核对`,
        });
        if (!prev.feedFile && inv.feedFile) {
          invoices[invoices.indexOf(prev)] = inv;
          byKey.set(key, inv);
        }
      } else dup++;
    }
    for (const w of part.warnings || []) {
      const k = `${w.type}|${w.sheet ?? ''}|${w.text}`;
      if (!warnings.some((x) => `${x.type}|${x.sheet ?? ''}|${x.text}` === k)) warnings.push(w);
    }
  }
  if (dup) warnings.push({ type: 'feedDup', text: `${dup} 张票在多个上传文件中重复且内容一致，只保留一份` });
  const unknownSheets = parts.flatMap((p) => p.summary?.unknownSheets ?? []);
  return { invoices, warnings, summary: { customers: hxgSummaryOf(invoices), unknownSheets } };
}

/** 行票面金额（生成口径） */
export function hxgLineAmount(ln, variant) {
  if (ln.kind === 'note') return 0;
  const tconf = HXG_VARIANTS[variant];
  const qty = ln.qty ?? 0;
  const price = ln.price ?? 0;
  if (ln.wm) return qty * price * 0.967 * 0.967; // buzz WM 拆行：单价×0.967 后金额再×0.967
  if (tconf.priceMode === 'plain') return qty * price * (ln.pct70 ? 0.7 : ln.pct30 ? 0.3 : 1) * (tconf.disc967 ? 0.967 : 1);
  return qty * price * 0.967; // f967 / plain967 / amt967 数值口径相同
}

/** 发票票面总额（生成口径，含 Less / 首期 / 续票汇总） */
export function hxgInvoiceTotal(inv) {
  const tconf = HXG_VARIANTS[inv.variant];
  const sub = inv.lines.reduce((s, l) => s + hxgLineAmount(l, inv.variant), 0);
  const T = tconf.totals;
  if (T.kind === 'less2') {
    const less = inv.less ?? [{ pct: 0.005, base: 'sub' }, { pct: 0.04, base: 'sub' }];
    let deducted = 0;
    for (const l of less) {
      // base 'sub' = 按 Total 计（彩星 0.5%/4%）；'afterLess' = 按扣完前面的余额计（迪奇 5%+3% 连扣）
      deducted += l.base === 'afterLess' ? (sub - deducted) * l.pct : sub * l.pct;
    }
    return sub - deducted;
  }
  if (T.kind === 'disc5') return sub * 0.95;
  if (T.kind === 'intl') return inv.firstPeriod ? sub * 0.5 : sub;
  return sub;
}

/* ================= 生成 ================= */

/** 模板 sheet 手术基类（固定版式：不动行结构，只覆写单元格） */
class TplSheet {
  constructor(parts) {
    const xml = parts.sheetXml;
    const sdStart = xml.indexOf('<sheetData');
    const sdTagEnd = xml.indexOf('>', sdStart) + 1;
    const sdEnd = xml.indexOf('</sheetData>');
    this.prefix = xml.slice(0, sdTagEnd);
    // 模板簿里的批注是文员备注（噪音）；拆分模板不带 VML 部件，
    // 保留 <legacyDrawing> 会生成悬空 rId（WPS 拒开）——连同批注一起剥掉
    this.suffix = xml.slice(sdEnd).replace(/<legacyDrawing\b[^>]*\/>/g, '');
    this.rows = new Map();
    for (const row of parseRows(xml.slice(sdTagEnd, sdEnd))) this.rows.set(row.r, row);
    this.commentsXml = null;
    this.vmlXml = null;
    this.relsXml = null;
  }
  cell(r, colIdx) { return this.rows.get(r)?.cells.get(colIdx) || null; }
  style(r, colIdx) { return styleOf(this.cell(r, colIdx)); }
}

/** 整行清空（留样式清残留），maxCol 以内的列清空、以外原样 */
function clearedRowCells(tpl, r, maxCol) {
  const row = tpl.rows.get(r);
  const cells = new Map();
  if (!row) return cells;
  for (const [ci, x] of row.cells) {
    if (ci > maxCol) { cells.set(ci, x); continue; }
    cells.set(ci, cEmpty(idxToCol(ci), r, styleOf(x)));
  }
  return cells;
}

/** 明细行单元格 */
function lineCellsHxg(tpl, tconf, C, r, ln) {
  const cells = new Map();
  // 套打参考的空白行混有白字、红字和大字体；所有新明细沿用首行同列样式。
  // 保留各行原高度和位置，避免后续货号变白不可见或金额格式漂移。
  const st = (ci) => tpl.style(tconf.preprinted ? tconf.detailFrom : r, ci);
  const cur = ln.cur ?? tconf.currency; // extra（其他款/模费）行可带币种覆盖（如 MAXX 用国际簿但 USD）
  const put = (ci, x) => cells.set(ci, x);
  const col = (ci) => idxToCol(ci);
  // 货号一律按文本写入（长数字货号如 示例编号/示例编号 写数字会被显示成 1E+09）
  const code = ln.code === null || ln.code === undefined ? ln.code : safeText(ln.code);
  if (C.desc2 && tconf.splitCode) {
    const segs = String(code ?? '').split('-');
    put(C.desc, cStr(col(C.desc), r, st(C.desc), segs[0] ?? ''));
    put(C.desc2, segs.length > 1 ? cStr(col(C.desc2), r, st(C.desc2), segs[1]) : cEmpty(col(C.desc2), r, st(C.desc2)));
  } else if (code === null || code === undefined || code === '') {
    put(C.desc, cEmpty(col(C.desc), r, st(C.desc)));
    if (C.desc2) put(C.desc2, cEmpty(col(C.desc2), r, st(C.desc2)));
  } else {
    put(C.desc, cStr(col(C.desc), r, st(C.desc), String(code)));
  }
  if (ln.kind === 'note') {
    for (const ci of [C.qty, C.pcs, C.cur1, C.price, C.cur2, C.amt, C.orig].filter(Boolean))
      put(ci, cEmpty(col(ci), r, st(ci)));
    return cells;
  }
  const qty = ln.qty ?? 0;
  const price = ln.price ?? 0;
  put(C.qty, cNum(col(C.qty), r, st(C.qty), qty));
  put(C.pcs, cStr(col(C.pcs), r, st(C.pcs), ln.pcs ?? tconf.pcs));
  put(C.cur1, cStr(col(C.cur1), r, st(C.cur1), cur));
  put(C.cur2, cStr(col(C.cur2), r, st(C.cur2), cur));
  const amtCol = col(C.amt);
  const priceCol = col(C.price);
  const qtyCol = col(C.qty);
  if (ln.wm) {
    // buzz WM 拆行（样票 示例编号）：金额右侧列（K）镜像来源价，单价==K*0.967，金额=数量×单价×0.967
    const origCi = C.amt + 1;
    const n = price * 0.967;
    put(C.price, cFormula(priceCol, r, st(C.price), `${col(origCi)}${r}*0.967`, n));
    put(C.amt, cFormula(amtCol, r, st(C.amt), `${qtyCol}${r}*${priceCol}${r}*0.967`, n * qty * 0.967));
    put(origCi, cNum(col(origCi), r, st(origCi), price));
    return cells;
  }
  if (tconf.priceMode === 'f967') {
    const n = price * 0.967;
    put(C.price, cFormula(priceCol, r, st(C.price), `${col(C.orig)}${r}*0.967`, n));
    put(C.amt, cFormula(amtCol, r, st(C.amt), `${qtyCol}${r}*${priceCol}${r}`, n * qty));
    put(C.orig, cNum(col(C.orig), r, st(C.orig), price));
  } else if (tconf.priceMode === 'plain967') {
    const n = price * 0.967;
    put(C.price, cNum(priceCol, r, st(C.price), n));
    put(C.amt, cNum(amtCol, r, st(C.amt), n * qty));
  } else if (tconf.priceMode === 'amt967') {
    put(C.price, cNum(priceCol, r, st(C.price), price));
    put(C.amt, cFormula(amtCol, r, st(C.amt), `${qtyCol}${r}*${priceCol}${r}*0.967`, qty * price * 0.967));
  } else { // plain：思信模全额不打折；intl/trade 按用户要求 ×0.967（disc967）；SHUSHUPAPA 70%/30%定金 行再 ×0.7/×0.3
    const p = price * (ln.pct70 ? 0.7 : ln.pct30 ? 0.3 : 1) * (tconf.disc967 ? 0.967 : 1);
    if (tconf.priceRefOrig) {
      put(C.price, cFormula(priceCol, r, st(C.price), `${col(C.orig)}${r}${tconf.disc967 ? '*0.967' : ''}`, p));
    } else {
      put(C.price, cNum(priceCol, r, st(C.price), p));
    }
    put(C.amt, cFormula(amtCol, r, st(C.amt), `${qtyCol}${r}*${priceCol}${r}`, p * qty));
    if (C.orig) put(C.orig, cNum(col(C.orig), r, st(C.orig), price)); // 右侧镜像保持原价
  }
  return cells;
}

/** 续票拆分：超容量分页（基号、基号-1…），非末页合计留空、末页跨页汇总（华康D 同规则） */
function paginateHxg(inv, cap) {
  if (inv.lines.length <= cap) return [{ ...inv }];
  const nPages = Math.ceil(inv.lines.length / cap);
  const pages = [];
  for (let p = 0; p < nPages; p++)
    pages.push({ ...inv, lines: inv.lines.slice(p * cap, (p + 1) * cap), pageNo: p, pageCnt: nPages, pageSrc: inv });
  return pages;
}

const SHEET_BAD_RE = /[[\]:*?/\\]/g;

/** XML 1.0 非法控制字符清洗：排期表长文本里夹的 \x02 等写进单元格会产生非法 XML
 *  （Excel/WPS 报「需要修复」，LibreOffice 直接解析失败把整页渲染丢样式，2026-10-20 示例编号 踩坑） */
const safeText = (s) => String(s).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');

/** 表头单元格覆写（抬头/S/N/票号/日期）。S/N 合同号一律写完整原串（含字母连字符），
 *  不写数字格——数字格太窄会显示 ###，文本格完整显示（2026-10-13 用户要求） */
function writeHeaderCells(tpl, tconf, inv, cells, r) {
  const put = (addr, make) => {
    const m = addr.match(/^([A-Z]+)(\d+)$/);
    if (+m[2] !== r) return;
    const ci = colToIdx(m[1]);
    cells.set(ci, make(idxToCol(ci), r, tpl.style(r, ci)));
  };
  if (tconf.buyerCell) {
    const hdr = HXG_HEADERS[inv.headerGroup];
    if (hdr) put(tconf.buyerCell, (c, rr, s) => cStr(c, rr, s, hdr));
  }
  if (tconf.snCell)
    put(tconf.snCell, (c, rr, s) => {
      if (inv.contract === null || inv.contract === undefined || inv.contract === '') return cEmpty(c, rr, s);
      return cStr(c, rr, s, safeText(inv.contract));
    });
  if (tconf.noCell)
    put(tconf.noCell, (c, rr, s) => {
      const raw = String(inv.invNo);
      if (tconf.noAsNumber && /^\d+(\.\d+)?$/.test(raw)) return cNum(c, rr, s, +raw);
      return cStr(c, rr, s, raw);
    });
  if (tconf.dateCell)
    put(tconf.dateCell, (c, rr, s) => (inv.date ? cNum(c, rr, s, inv.date) : cEmpty(c, rr, s)));
}

/** 合计区覆写 */
function writeTotalCells(tpl, tconf, inv, r, cells, { prevPages, isLastPage }) {
  const T = tconf.totals;
  const amtL = idxToCol(T.valCol);
  const st = (ci) => tpl.style(tconf.preprinted ? (ci === T.valCol || ci === T.curCol ? T.grandRow : tconf.detailFrom) : r, ci);
  const src = inv.pageSrc || inv;
  const range = `${amtL}${tconf.detailFrom}:${amtL}${tconf.detailTo}`;
  const prevRefs = prevPages.map((p) => `SUM('${p.nm}'!${range})`);
  const sumFormula = [...prevRefs, `SUM(${range})`].join('+');
  const subAll = src.lines.reduce((s, l) => s + hxgLineAmount(l, src.variant), 0);

  const setVal = (ci, f, v) => cells.set(ci, isLastPage ? cFormula(idxToCol(ci), r, st(ci), f, v) : cEmpty(idxToCol(ci), r, st(ci)));

  if (tconf.preprinted && isLastPage && (r === T.subRow || r === T.grandRow))
    cells.set(T.curCol, cStr(idxToCol(T.curCol), r, st(T.curCol), inv.currency || tconf.currency));

  if (T.kind === 'sum') {
    if (r === T.grandRow) {
      setVal(T.valCol, sumFormula, hxgInvoiceTotal(src));
      // extra（其他款/模费）票币种与模板标签不同时覆写（如 MAXX 用国际簿但 USD，模板模费 sheet 是 HK$）
      if (isLastPage && inv.currency && T.curCol != null)
        cells.set(T.curCol, cStr(idxToCol(T.curCol), r, st(T.curCol), inv.currency));
    }
    return;
  }
  if (T.kind === 'less2') {
    const less = src.less ?? [{ pct: 0.005, label: 'Less:0.5%', base: 'sub' }, { pct: 0.04, label: 'Less:4%', base: 'sub' }];
    if (r === T.subRow) { setVal(T.valCol, sumFormula, subAll); return; }
    if (r === T.grandRow) {
      const parts = less.map((_, k) => `-${amtL}${T.lessRows[k]}`).join('');
      setVal(T.valCol, `${amtL}${T.subRow}${parts}`, hxgInvoiceTotal(src));
      return;
    }
    const li = T.lessRows.indexOf(r);
    if (li >= 0) {
      const spec = less[li];
      if (!spec) {
        // 多余的 Less 行（迪奇单 5% 时第二行）：整行清空（含标签）
        for (const ci of [T.labelCol, T.curCol, T.valCol]) cells.set(ci, cEmpty(idxToCol(ci), r, st(ci)));
        return;
      }
      if (isLastPage) {
        cells.set(T.labelCol, cStr(idxToCol(T.labelCol), r, st(T.labelCol), spec.label));
        if (tconf.preprinted) cells.set(T.curCol, cStr(idxToCol(T.curCol), r, st(T.curCol), inv.currency || tconf.currency));
        const baseRef = spec.base === 'afterLess' ? `(${amtL}${T.subRow}-${less.slice(0, li).map((_, k) => `${amtL}${T.lessRows[k]}`).join('-')})` : `${amtL}${T.subRow}`;
        const prior = less.slice(0, li).reduce((s, l2) => s + (l2.base === 'afterLess' ? (subAll - s) * l2.pct : subAll * l2.pct), 0);
        const baseVal = spec.base === 'afterLess' ? subAll - prior : subAll;
        cells.set(T.valCol, cFormula(amtL, r, st(T.valCol), `${baseRef}*${spec.pct}`, baseVal * spec.pct));
      } else {
        for (const ci of [T.labelCol, T.curCol, T.valCol]) cells.set(ci, cEmpty(idxToCol(ci), r, st(ci)));
      }
    }
    return;
  }
  if (T.kind === 'disc5') {
    if (r === T.subRow) { setVal(T.valCol, sumFormula, subAll); return; }
    if (r === T.discRow) {
      if (tconf.preprinted && isLastPage) cells.set(T.labelCol, cStr(idxToCol(T.labelCol), r, st(T.labelCol), 'Less:5%'));
      setVal(T.valCol, `${amtL}${T.subRow}*0.05`, subAll * 0.05); return;
    }
    if (r === T.grandRow) { setVal(T.valCol, `${amtL}${T.subRow}-${amtL}${T.discRow}`, hxgInvoiceTotal(src)); return; }
    return;
  }
  if (T.kind === 'intl') {
    if (r === T.subRow) { setVal(T.valCol, sumFormula, subAll); return; }
    if (r === T.grandRow) {
      const ref = inv.firstPeriod ? `${amtL}${T.periodRows[1]}` : `${amtL}${T.subRow}`;
      setVal(T.valCol, ref, hxgInvoiceTotal(src));
      return;
    }
    const pr = T.periodRows.indexOf(r);
    if (pr >= 0 && inv.firstPeriod && isLastPage) {
      if (pr === 0) {
        cells.set(T.labelCol, cStr(idxToCol(T.labelCol), r, st(T.labelCol), '（首期50%）'));
        cells.set(T.valCol, cFormula(amtL, r, st(T.valCol), `${amtL}${T.subRow}*0.5`, subAll * 0.5));
      }
      if (pr === 1) {
        cells.set(T.valCol, cFormula(amtL, r, st(T.valCol), `${amtL}${T.periodRows[0]}`, subAll * 0.5));
        cells.set(T.curCol, cStr(idxToCol(T.curCol), r, st(T.curCol), tconf.currency)); // 样票 I44=USD
      }
    }
    return;
  }
}

/** 生成一张 sheet 的 XML；套打时使用独立预印纸模板，保留交易值及动态扣款说明。 */
function buildHxgSheet(tpl, tconf, inv, ctx) {
  const out = [];
  const totalRows = [];
  const T = tconf.totals;
  if (T.kind === 'less2') totalRows.push(T.subRow, ...T.lessRows, T.grandRow);
  else if (T.kind === 'disc5') totalRows.push(T.subRow, T.discRow, T.grandRow);
  else if (T.kind === 'intl') totalRows.push(T.subRow, T.grandRow, ...T.periodRows);
  else totalRows.push(T.grandRow);
  const headerRows = new Set(
    [tconf.buyerCell, tconf.snCell, tconf.noCell, tconf.dateCell]
      .filter(Boolean)
      .map((a) => +a.match(/\d+/)[0]),
  );
  const refM = tconf.refCell ? tconf.refCell.match(/^([A-Z]+)(\d+)$/) : null;
  const refRow = refM ? +refM[2] : null;
  const refCi = refM ? colToIdx(refM[1]) : null;
  const headByRow = new Map(); // r -> [colIdx...]
  if (ctx.noHead) {
    for (const a of tconf.headCells || []) {
      const m = a.match(/^([A-Z]+)(\d+)$/);
      if (!headByRow.has(+m[2])) headByRow.set(+m[2], []);
      headByRow.get(+m[2]).push(colToIdx(m[1]));
    }
  }
  for (const [r, row] of [...tpl.rows.entries()].sort((a, b) => a[0] - b[0])) {
    let cells;
    if (r >= tconf.detailFrom && r <= tconf.detailTo) {
      cells = clearedRowCells(tpl, r, tconf.maxCol);
      const li = r - tconf.detailFrom;
      if (li < inv.lines.length) {
        const lc = lineCellsHxg(tpl, tconf, tconf.cols, r, inv.lines[li]);
        for (const [ci, x] of lc) cells.set(ci, x);
      }
    } else if (totalRows.includes(r) || headerRows.has(r) || r === refRow || headByRow.has(r)) {
      cells = new Map(row.cells);
      if (totalRows.includes(r)) writeTotalCells(tpl, tconf, inv, r, cells, ctx);
      if (headerRows.has(r)) writeHeaderCells(tpl, tconf, inv, cells, r);
      // 记录原始总金额（未打折），红色字体，打印区域右方第二列（模板构建时已注入红样式空格）
      if (r === refRow && refCi !== null && inv.refTotal !== null && inv.refTotal !== undefined)
        cells.set(refCi, cNum(idxToCol(refCi), r, tpl.style(r, refCi), inv.refTotal));
      if (headByRow.has(r))
        for (const ci of headByRow.get(r)) cells.set(ci, cEmpty(idxToCol(ci), r, tpl.style(r, ci)));
    } else {
      cells = new Map(row.cells);
    }
    out.push(rowXml(r, row.attrs, cells));
  }
  const lastRow = Math.max(...totalRows);
  const prefix = tpl.prefix
    .replace(/<dimension ref="[^"]*"\/>/, `<dimension ref="A1:${tconf.preprinted ? 'N' : 'IW'}${lastRow}"/>`)
    .replace(/tabSelected="true"/, 'tabSelected="false"');
  return prefix + out.join('') + tpl.suffix;
}

/**
 * 生成全部输出文件（每个客户一个货款文件；有其他款/模费票的客户再出一个 extra 文件）。
 * @param parsed parseHxgRecords 的结果（或手工构造的同形对象）
 * @param tplBuffers { 模板文件名: ArrayBuffer }（键 = HXG_TPL_SHEETS 的文件名）
 * @param opts { customers?: string[], yms?: (string|null)[], noHead?: boolean|'auto' }
 * noHead=true 使用《大陆格式.xls》预印纸套打格式；auto按客户判定，false/未传沿用完整格式。
 * @returns Promise<[{ label, fileName, buffer, sheetCount, invoices }]>
 */
export async function generateHxgFiles(parsed, tplBuffers, opts = {}) {
  const groups = new Map(); // customer -> { goods: [], extra: [] }
  for (const inv of parsed.invoices) {
    if (opts.customers && !opts.customers.includes(inv.customer)) continue;
    if (opts.yms && opts.yms.length && !opts.yms.includes(inv.ym)) continue;
    if (!groups.has(inv.customer)) groups.set(inv.customer, { goods: [], extra: [] });
    groups.get(inv.customer)[inv.extra ? 'extra' : 'goods'].push(inv);
  }
  const out = [];
  for (const [customer, g] of groups) {
    const conf = HXG_CUSTOMERS[customer];
    if (!conf) continue;
    const safe = customer.replace(/[\\/:*?"<>|]/g, '_');
    if (g.goods.length)
      out.push(await buildHxgBook(conf, conf.tplFile, customer, `华兴_${safe}发票.xlsx`, g.goods, tplBuffers, opts));
    if (g.extra.length) {
      const tplFile = HXG_EXTRA_TPL[HXG_EXTRA_FORMAT[customer]];
      out.push(await buildHxgBook(conf, tplFile, `${customer}其他款模费`, `华兴_${safe}其他款及模费发票.xlsx`, g.extra, tplBuffers, opts));
    }
  }
  return out;
}

/** 单本输出工作簿（一组发票 → 一个文件）：模板加载 → 分页 → 逐 sheet 生成 */
async function buildHxgBook(conf, tplFile, label, fileName, list0, tplBuffers, opts) {
  const noHead = opts.noHead === 'auto' ? HXG_NOHEAD_CUSTOMERS.has(list0[0].customer) : !!opts.noHead;
  const actualTplFile = noHead ? HXG_PREPRINTED_TPL : tplFile;
  const buf = tplBuffers[actualTplFile];
  if (!buf) throw new Error(`缺模板「${actualTplFile}」`);
  const pkg = await XlsxPackage.load(buf);
  // 该文件用到的变体 → 模板 sheet
  const tpls = new Map();
  const layoutOf = (variant) => noHead ? preprintedLayout(HXG_VARIANTS[variant]) : HXG_VARIANTS[variant];
  for (const vkey of new Set(list0.map((inv) => inv.variant))) {
    const tconf = layoutOf(vkey);
    tpls.set(vkey, new TplSheet(await pkg.getTemplateParts(tconf.sheet)));
  }
  await pkg.stripAllSheets();
  const usedNames = new Set();
  const pageAcc = new Map();
  const pages = [];
  for (const inv of list0) {
    const tconf = layoutOf(inv.variant);
    const cap = tconf.detailTo - tconf.detailFrom + 1;
    pages.push(...paginateHxg(inv, cap));
  }
  for (const inv of pages) {
    const tconf = layoutOf(inv.variant);
    const tpl = tpls.get(inv.variant);
    if (!tpl) throw new Error(`模板文件「${tplFile}」里没有变体「${inv.variant}」的 sheet`);
    const prevPages = inv.pageCnt > 1 && inv.pageNo > 0 ? (pageAcc.get(inv.pageSrc) || []) : [];
    const isLastPage = !inv.pageCnt || inv.pageNo === inv.pageCnt - 1;
    const invWithHeader = { ...inv, headerGroup: conf.header };
    const sheetXml = buildHxgSheet(tpl, tconf, invWithHeader, { prevPages, isLastPage, noHead });
    let nm = String(inv.invNo).replace(SHEET_BAD_RE, '_');
    if (inv.pageNo) nm = `${nm}-${inv.pageNo}`;
    nm = nm.slice(0, 31);
    let k = 2;
    while (usedNames.has(nm)) nm = `${String(inv.invNo).replace(SHEET_BAD_RE, '_').slice(0, 28)}~${k++}`;
    usedNames.add(nm);
    inv.sheetName = nm;
    inv.ledgerTotal = isLastPage ? hxgInvoiceTotal(inv.pageSrc || inv) : null;
    if (inv.pageCnt > 1 && !isLastPage) {
      const arr = pageAcc.get(inv.pageSrc) || [];
      arr.push({ nm });
      pageAcc.set(inv.pageSrc, arr);
    }
    pkg.addSheet({
      name: nm, sheetXml,
      commentsXml: null, vmlXml: null, relsXml: null, definedNames: true,
      printArea: `$A$1:$${idxToCol(tconf.totals.valCol)}$${tconf.totals.grandRow}`,
      // 套打沿用独立模板经打印验收的参数，不再套用其他票型的统一设置。
      printFit: !noHead,
    });
  }
  const buffer = await pkg.save({ fullCalcOnLoad: true });
  return { label, fileName, buffer, sheetCount: pages.length, invoices: pages };
}
