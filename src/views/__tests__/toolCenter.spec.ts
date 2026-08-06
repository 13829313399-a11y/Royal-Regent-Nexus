import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { navigationGroups } from '@/data/enterpriseMock'


describe('public tool center', () => {
  it('places the shared toolbar between main and cross-factory navigation', () => {
    const labels = navigationGroups.map((group) => group.label)
    expect(labels.indexOf('TOOLS')).toBe(labels.indexOf('MAIN') + 1)
    expect(labels.indexOf('TOOLS')).toBeLessThan(labels.indexOf('CROSS FACTORY'))
    expect(navigationGroups.find((group) => group.label === 'TOOLS')?.items).toContainEqual(
      expect.objectContaining({
        label: '公共工具栏',
        to: '/tools',
        preserveFactory: true,
      }),
    )
  })

  it('registers an authenticated tool-center route and all reusable PDF modules', () => {
    const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
    const viewSource = readFileSync(join(process.cwd(), 'src/views/ToolCenterView.vue'), 'utf8')
    const excelSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfToExcelTool.vue'), 'utf8')
    const wordSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfToWordTool.vue'), 'utf8')
    const splitSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfSplitTool.vue'), 'utf8')

    expect(routerSource).toContain("path: '/tools'")
    expect(routerSource).toContain("component: () => import('@/views/ToolCenterView.vue')")
    expect(viewSource).toContain('<PdfToExcelTool')
    expect(viewSource).toContain('<PdfToWordTool')
    expect(viewSource).toContain('<PdfSplitTool')
    expect(viewSource).toContain('PDF 转 Word')
    expect(viewSource).toContain('PDF 拆分')
    expect(excelSource).toContain('sharedToolsApi.convertPdfToExcel')
    expect(wordSource).toContain('sharedToolsApi.convertPdfToWord')
    expect(wordSource).toContain('文件仅用于本次转换')
    expect(splitSource).toContain('sharedToolsApi.splitPdf')
    expect(splitSource).toContain('按指定页段拆分')
  })
})
