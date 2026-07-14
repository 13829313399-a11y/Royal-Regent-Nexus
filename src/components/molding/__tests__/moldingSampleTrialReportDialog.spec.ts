import { expect, test } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const dialogSource = readFileSync(
  join(process.cwd(), 'src/components/molding/MoldingSampleTrialReportDialog.vue'),
  'utf8',
)
const sheetSource = readFileSync(
  join(process.cwd(), 'src/components/molding/MoldingSampleTrialReportSheet.vue'),
  'utf8',
)

test('trial report dialog includes filling, A4 printing, and factory receipt content', () => {
  for (const requiredCopy of [
    '试模报告填写 / 打印',
    '工模试模（交模）验收回执',
    '原纸质《工模试模（交模）验收回执》版式',
    '工程资料会自动带入，啤机部直接在原表格对应位置填写',
    '预览 / 打印',
    '保存试模报告',
    '试模报告历史 / 打印',
    '啤机部已保存并同步至工程部',
    '返回历史',
  ]) {
    expect(dialogSource).toMatch(new RegExp(requiredCopy))
  }

  for (const requiredImplementation of [
    'molding-sample-trial-report-dialog',
    'molding-sample-trial-report-print-preview',
    'molding-sample-trial-report-print-area',
    'molding-sample-trial-report-printing',
    'window.print\\(\\)',
    'MoldingSampleTrialReportSheet',
    '放大报告',
    '恢复原尺寸',
    'molding-sample-trial-report-zoom-canvas',
    'editable',
    '@update:data',
    'size: A4 portrait',
    'readOnly',
    'initialItemId',
    ':editable="!readOnly"',
  ]) {
    expect(dialogSource).toMatch(new RegExp(requiredImplementation))
  }

  for (const requiredSheetCopy of [
    'R-234',
    'V-1.0',
    '致：啤机部',
    '模具供应商',
    '全原料',
    '全水口料',
    '水口比例',
    '样板类别',
    '颜色',
    '色粉编号',
    'report-ratio-control',
    '特别要求',
    '试模要求',
    '试模参数：（由啤机部填写）',
    '适配机型',
    '安士（A）',
    '顶针次数',
    '锁模压力',
    '手动',
    '冻水',
    '热水',
    '冰水',
    '模具问题记录事项',
    '模具问题',
    '胶件问题',
    '试模总结',
    '不合格试模（退模厂改模）',
    'width: 210mm',
    'height: 297mm',
    'size: A4 portrait',
    'body.molding-sample-trial-report-printing > *',
    'break-after: avoid-page',
    'page-break-after: avoid',
  ]) {
    expect(sheetSource).toMatch(new RegExp(requiredSheetCopy))
  }

  expect(sheetSource).not.toContain('颜色 / 色粉编号')
  expect(sheetSource).not.toContain('工程明细')
})
