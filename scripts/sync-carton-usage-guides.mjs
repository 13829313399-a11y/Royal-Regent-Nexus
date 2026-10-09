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
    '从纸箱采购协同页面右上角的“使用教程”打开图文说明，可查找步骤、进入对应页面，并使用“打印 / 保存 PDF”。首次启用先核对基础资料和期初结余，历史订单按需衔接；每天从工作看板开始。供应商操作见[供应商协同使用教程](纸箱供应商协同使用教程.md)。',
    'workflow.svg', cartonGuideSections, cartonDailyChecklist)],
  ['纸箱供应商协同使用教程.md', render('纸箱供应商协同使用教程',
    '从纸箱供应商协同页面右上角的“使用教程”打开，可查找步骤、进入对应供应商页面，并使用“打印 / 保存 PDF”。先核对采购与目的厂区，再接单、登记真实发货、跟进仓库反馈；双方核对同一份月结版本。内部仓管操作见[纸箱模块使用教程](纸箱模块使用教程.md)。',
    'supplier-workflow.svg', cartonSupplierGuideSections, cartonSupplierChecklist)],
]
for (const [name, content] of documents) {
  const url = new URL('../docs/business/' + name, import.meta.url)
  if (process.argv.includes('--check')) {
    if (await readFile(url, 'utf8') !== content) throw new Error(name + ' 与页面教程内容不一致，请运行 node scripts/sync-carton-usage-guides.mjs')
  } else await writeFile(url, content, 'utf8')
  console.log(name + (process.argv.includes('--check') ? '：内容一致' : '：已同步'))
}
