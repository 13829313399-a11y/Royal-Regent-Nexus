import { readFile, writeFile } from 'node:fs/promises'
import { cartonGuideSections, cartonDailyChecklist } from '../src/features/carton-procurement/usageGuide.ts'
import { cartonSupplierGuideSections, cartonSupplierChecklist } from '../src/features/carton-procurement/supplierUsageGuide.ts'

function render(title, introduction, image, sections, checklist) {
  const output = [
    '# ' + title, '', introduction, '',
    '![' + title + '操作顺序](../../public/carton-guide/' + image + ')', '',
    '配图为操作示意及演示数据，实际办理以目的厂区、账号权限和真实业务为准。', '',
  ]
  for (const section of sections) {
    output.push('## ' + section.number + ' ' + section.title, '',
      '**' + section.group + ' · 位置：' + section.entry + '**', '', section.summary, '')
    if (section.image) output.push('![' + section.image.alt + '](' + section.image.src.replace('/carton-guide/', '../../public/carton-guide/') + ')', '', section.image.caption, '')
    section.steps.forEach((step, i) => output.push((i + 1) + '. ' + step))
    output.push('')
    if (section.table) {
      output.push('| ' + section.table.columns.join(' | ') + ' |',
        '| ' + section.table.columns.map(() => '---').join(' | ') + ' |')
      section.table.rows.forEach(row => output.push('| ' + row.join(' | ') + ' |'))
      output.push('')
    }
    output.push('**完成后检查：** ' + section.result, '', '**操作时留意：**', '')
    section.reminders.forEach(reminder => output.push('- ' + reminder))
    output.push('')
  }
  output.push('## 每天收尾检查', '', '勾选仅用于自查，不会修改业务记录。', '')
  checklist.forEach(item => output.push('- [ ] ' + item))
  output.push('')
  return output.join('\n')
}

const documents = [
  ['纸箱模块使用教程.md', render('纸箱模块使用教程',
    '先选对厂区，再按每章的 1 → 2 → 3 办理。首次试点先定切换日期、备份旧表、盘点实物，分清现存和待收；日常先查原单，再下单、验收和出库。遇到报错留单号和截图，先查结果，别重复提交。页面右上角“使用教程”可查找步骤、打开对应页面和“打印 / 保存 PDF”。供应商请看[供应商协同使用教程](纸箱供应商协同使用教程.md)。',
    'workflow.svg', cartonGuideSections, cartonDailyChecklist)],
  ['纸箱供应商协同使用教程.md', render('纸箱供应商协同使用教程',
    '先选对目的厂区，核对当前采购后接单，按真实数量发货，再看仓库实际验收结果。本月对账只读，先核对厂区、月份和币种，有差异回原单查。报错先查是否成功，别重复接单或发货。页面右上角“使用教程”可查找步骤和“打印 / 保存 PDF”。仓管请看[纸箱模块使用教程](纸箱模块使用教程.md)。',
    'supplier-workflow.svg', cartonSupplierGuideSections, cartonSupplierChecklist)],
]
for (const [name, content] of documents) {
  const url = new URL('../docs/business/' + name, import.meta.url)
  if (process.argv.includes('--check')) {
    if (await readFile(url, 'utf8') !== content) throw new Error(name + ' 与页面教程内容不一致，请运行 node scripts/sync-carton-usage-guides.mjs')
  } else await writeFile(url, content, 'utf8')
  console.log(name + (process.argv.includes('--check') ? '：内容一致' : '：已同步'))
}
