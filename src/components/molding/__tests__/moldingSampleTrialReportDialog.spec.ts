import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, expect, test, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import MoldingSampleTrialReportDialog from '@/components/molding/MoldingSampleTrialReportDialog.vue'
import type { MoldingSampleItem, MoldingSampleOrder } from '@/types/moldingSample'

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
    'await nextTick\\(\\)',
    'document.fonts',
    'waitForPrintLayout',
    'requestAnimationFrame',
    'printRoot.isConnected',
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
    "\\['华康A', '华康B'\\]",
    "'东源'",
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
    'body.molding-sample-trial-report-printing > *',
    'body.molding-sample-trial-report-printing \\{ width: 210mm',
    'left: -10000px',
    'visibility: hidden',
    'visibility: visible !important',
    'break-after: avoid-page',
    'page-break-after: avoid',
  ]) {
    expect(sheetSource).toMatch(new RegExp(requiredSheetCopy))
  }

  expect(sheetSource).not.toContain('颜色 / 色粉编号')
  expect(sheetSource).not.toContain('工程明细')
  expect(sheetSource).not.toMatch(/@media print \{[^}]*html, body/)
})

const orderFixture: MoldingSampleOrder = {
  id: 'BP-PRINT-001',
  factory_id: 'huaxing',
  order_number: 'P50002008',
  doc_number: 'W-G026-00',
  product_name: '30寸黑武士',
  client_name: 'ShuShuPaPa',
  date: '2026-07-16',
  stage: 'T0',
  order_type: '啤办',
  workshop: 'A车间',
  send_to: '',
  supervisor: '主管',
  eng_name: '工程员',
  reason: '试模确认',
  status: '待生产',
  reject_reason: '',
  completed_date: '',
  created_at: '2026-07-16T08:00:00Z',
  updated_at: '2026-07-16T08:00:00Z',
}

const itemFixture: MoldingSampleItem = {
  id: 'item-print-001',
  order_id: orderFixture.id,
  sort_order: 1,
  mold_id: 'P50002008-01-01',
  mold_name: '黑武士头部',
  mold_dimensions: '650 × 450 × 380 mm',
  mold_presence_status: 'in_factory',
  machine_type: '',
  production_machine: '',
  material: 'PP K7100',
  color: '黑色',
  pigment_no: 'PMS Black',
  quantity: '1/1',
  shoot_qty: 20,
  gross_weight_g: null,
  required_material_kg: 7,
  mold_return_time: '',
  completion_time: '2026-07-18',
  notes: '',
  receipt_no: '',
  collected_weight_kg: null,
  actual_weight_kg: null,
  actual_amount_hkd: null,
  injection_cost: null,
  injection_cost_hkd: null,
  exchange_rate_at_save: null,
}

function mountDialog(factoryShortName: string) {
  return mount(MoldingSampleTrialReportDialog, {
    attachTo: document.body,
    props: {
      visible: true,
      order: orderFixture,
      items: [itemFixture],
      reports: [],
      factoryShortName,
      operatorName: '啤机员',
      canSave: true,
      saving: false,
    },
  })
}

function findButton(label: string) {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
    .find((entry) => entry.textContent?.trim() === label)

  if (!button) {
    throw new Error(`Button not found: ${label}`)
  }

  return button
}

afterEach(() => {
  document.body.className = ''
  document.body.innerHTML = ''
  document.getElementById('molding-sample-active-print-page')?.remove()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('trial report uses Dongyuan for Huakang A and B while retaining Heyuan elsewhere', async () => {
  const wrapper = mountDialog('华康A')
  await nextTick()
  expect(document.body.textContent).toContain('华康A（东源）玩具制品有限公司')

  await wrapper.setProps({ factoryShortName: '华康B' })
  expect(document.body.textContent).toContain('华康B（东源）玩具制品有限公司')

  await wrapper.setProps({ factoryShortName: '华兴' })
  expect(document.body.textContent).toContain('华兴（河源）玩具制品有限公司')
  wrapper.unmount()
})

test('first trial-report print waits for two layout frames and prints a populated root', async () => {
  const frames: FrameRequestCallback[] = []
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.push(callback)
    return frames.length
  })

  let stateAtPrint: { bodyClass: boolean, pageStyle: boolean, hasContent: boolean } | undefined
  const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {
    const printRoot = document.querySelector<HTMLElement>('[data-testid="molding-sample-trial-report-print-area"]')
    stateAtPrint = {
      bodyClass: document.body.classList.contains('molding-sample-trial-report-printing'),
      pageStyle: document.getElementById('molding-sample-active-print-page')?.textContent?.includes('A4 portrait') === true,
      hasContent: Boolean(printRoot?.firstElementChild?.textContent?.includes('工模试模（交模）验收回执')),
    }
    window.dispatchEvent(new Event('afterprint'))
  })

  const wrapper = mountDialog('华兴')
  findButton('预览 / 打印').click()
  await nextTick()

  findButton('确认打印').click()
  expect(printSpy).not.toHaveBeenCalled()
  expect(document.body.classList.contains('molding-sample-trial-report-printing')).toBe(true)

  await nextTick()
  await Promise.resolve()
  expect(frames).toHaveLength(1)
  frames.shift()?.(0)
  await Promise.resolve()
  expect(printSpy).not.toHaveBeenCalled()
  expect(frames).toHaveLength(1)
  frames.shift()?.(16)
  await Promise.resolve()
  await nextTick()

  expect(printSpy).toHaveBeenCalledTimes(1)
  expect(stateAtPrint).toEqual({ bodyClass: true, pageStyle: true, hasContent: true })
  expect(document.body.classList.contains('molding-sample-trial-report-printing')).toBe(false)
  expect(document.getElementById('molding-sample-active-print-page')).toBeNull()
  wrapper.unmount()
})
