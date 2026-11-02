import { readFile, writeFile } from 'node:fs/promises'
import { cartonGuideSections } from '../src/features/carton-procurement/usageGuide.ts'
import { cartonSupplierGuideSections } from '../src/features/carton-procurement/supplierUsageGuide.ts'

// Deterministic SVG diagrams, shared by the in-app reader and printable manuals.
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')
function lines(text, width) {
  const result = []; let line = '', used = 0
  for (const char of text.match(/\d+(?:\.\d+)?|[A-Za-z]+|./gu) ?? []) {
    const size = Array.from(char).reduce((sum, c) => sum + (c.charCodeAt(0) > 255 ? 1 : 0.55), 0)
    if (used + size > width && !/^[，。；、：！？）”]$/.test(char)) { result.push(line); line = ''; used = 0 }
    line += char; used += size
  }
  if (line) result.push(line)
  return result
}
function textBlock(text, x, y, width, size = 20, color = '#334155') {
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${color}">${lines(text, width).map((line, i) => `<tspan x="${x}" dy="${i ? size * 1.6 : 0}">${escape(line)}</tspan>`).join('')}</text>`
}
function diagram(section) {
  const custom = examples(section.id)
  const cards = section.steps.map((step, i) => {
    const x = 28 + i * 348
    if (lines(step, 14).length > 6) throw new Error(`${section.id}: diagram step too long`)
    return `<rect x="${x}" y="100" width="328" height="266" rx="16" fill="white" stroke="#cbd5e1"/>
      <circle cx="${x + 36}" cy="134" r="18" fill="#0f766e"/>
      <text x="${x + 36}" y="141" text-anchor="middle" fill="white" font-size="21" font-weight="700">${i + 1}</text>
      <text x="${x + 66}" y="141" fill="#0f766e" font-size="19" font-weight="700">${['先打开 / 选择', '再填写 / 核对', '最后处理 / 检查'][i]}</text>
      ${textBlock(step, x + 22, 185, 14)}
      ${i < 2 ? `<path d="M${x + 332} 227 h10 m-4 -5 5 5 -5 5" stroke="#0f766e" fill="none" stroke-width="2"/>` : ''}`
  }).join('')
  const result = textBlock(section.result, 48, 408, 47, 20, '#115e59')
  if (lines(section.result, 47).length > 2) throw new Error(`${section.id}: result too long`)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="470" viewBox="0 0 1080 470" role="img" aria-labelledby="title desc">
  <title id="title">${escape(section.title)}</title><desc id="desc">${escape(section.steps.join('；'))}</desc>
  <rect width="1080" height="470" rx="20" fill="#f1f5f9"/>
  <g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif">
    <text x="28" y="43" font-size="27" font-weight="700" fill="#0f172a">${escape(section.title)}</text>
    <text x="28" y="74" font-size="17" fill="#64748b">操作示意 · 按 1 → 2 → 3 办理，具体按钮以当前页面为准</text>
    ${custom || cards}<rect x="28" y="382" width="1024" height="70" rx="12" fill="#ccfbf1"/>${result}
  </g></svg>\n`
}

function examples(id) {
  const label = (text, x, y, size = 22, color = '#334155') => `<text x="${x}" y="${y}" font-size="${size}" fill="${color}">${escape(text)}</text>`
  const panel = '<rect x="28" y="100" width="1024" height="266" rx="16" fill="white" stroke="#cbd5e1"/>'
  if (id === 'batch-append') return panel +
    label('① 勾选原订单     →     ② 填本次追加     →     ③ 核对后确认', 52, 136, 23, '#0f766e') +
    '<path d="M52 193 H1028 M52 252 H1028 M52 310 H1028" stroke="#e2e8f0"/>' +
    ['原订单（示例）', '当前需求', '本次追加', '追加后总需求'].map((t,i)=>label(t,52+i*250,180,19)).join('') +
    ['A 单 · 外箱', '100 个', '+ 20 个', '120 个'].map((t,i)=>label(t,52+i*250,232,24,i===3?'#0f766e':'#334155')).join('') +
    ['B 单 · 卡纸', '200 张', '+ 30 张', '230 张'].map((t,i)=>label(t,52+i*250,289,24,i===3?'#0f766e':'#334155')).join('') +
    label('两张单各自追加，不合单。已收数量不变；已发订单需供应商核对新版本。',52,344,20)
  if (id === 'demand-import') return panel +
    label('① 下载模板填写    →    ② 导入预览、修正    →    ③ 生成草稿',52,136,23,'#0f766e') +
    '<rect x="52" y="158" width="570" height="154" rx="8" fill="#f8fafc"/><path d="M52 194 H622 M52 233 H622 M52 272 H622" stroke="#cbd5e1"/>' +
    ['分组编号','订单类型','纸品','数量'].map((t,i)=>label(t,68+i*137,184,18)).join('') +
    [['A','样板单','外箱','20 个'],['A','样板单','卡纸','20 张'],['B','杂单','内箱','50 个']].map((r,j)=>r.map((t,i)=>label(t,68+i*137,221+j*39,20)).join('')).join('') +
    label('→',646,240,28,'#0f766e') +
    '<rect x="697" y="169" width="325" height="59" rx="10" fill="#ccfbf1"/><rect x="697" y="245" width="325" height="59" rx="10" fill="#e0f2fe"/>' +
    label('A：1 张样板单，2 项纸品',714,205,22,'#115e59') + label('B：1 张杂单，1 项纸品',714,281,22,'#075985') +
    label('分组示例；规格、单位和日期也需填写。生成草稿后，再核对并发给供应商。',52,344,20)
  if (['monthly','supplier-monthly'].includes(id)) return panel +
    label('① 选厂区 / 月份 / 币种   →   ② 看金额和明细   →   ③ 差异回原单处理',52,136,22,'#0f766e') +
    [['已验收送货','10,000 元'],['退货贷项','1,000 元'],['本月应结','9,000 元']].map((r,i)=>
      `<rect x="${52+i*340}" y="166" width="296" height="126" rx="12" fill="${i===2?'#ccfbf1':'#f1f5f9'}"/>` + label(r[0],76+i*340,205,20) + label(r[1],76+i*340,254,34,i===2?'#0f766e':'#0f172a')).join('') +
    label('−',355,240,32,'#0f766e') + label('＝',694,240,29,'#0f766e') +
    label('金额为示例。本页只读，无需系统内确认；付款、收款和库存月结另办。',52,344,20)
  return ''
}

const overviews = [
 {id:'workflow', title:'内部端：跟着真实业务走', steps:['下单：新需求建订单；样板／杂单可导入。多张旧单加量，用批量追加。','收发：供应商接单送货，仓库核对后入库；实际领料再出库。','对账：月底看送货、退货和应结金额；有差异回原单处理。'], result:'首次启用先准备基础资料和期初库存。一批货只入库一次。'},
 {id:'supplier-workflow', title:'供应商端：接单 → 送货 → 对账', steps:['接单：确认厂区，核对当前采购版本、纸品、数量和承诺交期。','送货：导入原送货单，核对数量和原价，再查看仓库有效入库与拒收反馈。','对账：选月份和币种，核对送货金额、退货贷项和本月应结。'], result:'本月对账只读，不需要系统内确认；收款另看“应付与收款”。'},
]
for (const section of [...cartonGuideSections, ...cartonSupplierGuideSections, ...overviews]) {
  const file = section.image?.src.split('/').at(-1) ?? section.id + '.svg'
  const url = new URL('../public/carton-guide/' + file, import.meta.url)
  const content = diagram(section)
  if (process.argv.includes('--check')) {
    if (await readFile(url, 'utf8') !== content) throw new Error(file + ' 图文不同步，请运行 node scripts/render-carton-guide-diagrams.mjs')
  } else await writeFile(url, content, 'utf8')
}
console.log(`教程配图${process.argv.includes('--check') ? '检查通过' : '已生成'}：${cartonGuideSections.length + cartonSupplierGuideSections.length + overviews.length} 张`)
