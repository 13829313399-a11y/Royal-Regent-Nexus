import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/IndonesiaInvoiceReconciliationView.vue'), 'utf8')
const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('Indonesia invoice reconciliation workspace', () => {
  it('uses an independent full-page route instead of the generic module detail', () => {
    expect(routerSource).toMatch(/path: '\/modules\/accounting\/indonesia-invoice-reconciliation'/)
    expect(routerSource).toMatch(/IndonesiaInvoiceReconciliationView\.vue/)
    expect(routerSource).toMatch(/title: '印尼票据核对'[\s\S]{0,100}fullPage: true/)
  })

  it('accepts two neutral A/B PDF inputs and renders field-level, source-labelled reconciliation results', () => {
    expect(source).toMatch(/印尼票据核对/)
    expect(source).toMatch(/导入两份 PDF/)
    expect(source).toMatch(/导入 PDF 文件 A/)
    expect(source).toMatch(/导入 PDF 文件 B/)
    expect(source).toMatch(/点击选择或拖拽 PDF 至此/)
    expect(source).toMatch(/function dropFile\(side: InvoiceFileSide, event: DragEvent\)/)
    expect(source).toMatch(/@drop\.prevent="dropFile\('a', \$event\)"/)
    expect(source).toMatch(/@drop\.prevent="dropFile\('b', \$event\)"/)
    expect(source).toMatch(/仅支持导入 PDF 文件/)
    expect(source).toMatch(/PDF A、B 不分客户票或供应商票/)
    expect(source).toMatch(/自动判断客户票与供应商票/)
    expect(source).toMatch(/PDF 仅用于本次核对，完成后不保存/)
    expect(source).toMatch(/indonesiaInvoiceApi\.reconcileRri/)
    expect(source).toMatch(/invoiceA: invoiceAFile\.value/)
    expect(source).toMatch(/invoiceB: invoiceBFile\.value/)
    expect(source).toMatch(/票据组数/)
    expect(source).toMatch(/已完成核对/)
    expect(source).toMatch(/待人工复核/)
    expect(source).toMatch(/票据金额汇总/)
    expect(source).toMatch(/全车间共享/)
    expect(source).toMatch(/施信客户两种票据版式已接入/)
    expect(source).toMatch(/当前客户规则：/)
    expect(source).toMatch(/不按车间区分/)
    expect(source).toMatch(/客户单价/)
    expect(source).toMatch(/单价先保留 4 位小数，再乘数量并保留 2 位金额/)
    expect(source).toMatch(/先看差异，再看全部明细/)
    expect(source).toMatch(/哪一张票的字段不一致，一眼可见/)
    expect(source).toMatch(/差异行置顶，直接定位到单价或金额/)
    expect(source).toMatch(/供应商单价异常/)
    expect(source).toMatch(/供应商行金额异常/)
  })
})
