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

  it('registers an authenticated tool-center route and a reusable PDF module', () => {
    const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
    const viewSource = readFileSync(join(process.cwd(), 'src/views/ToolCenterView.vue'), 'utf8')
    const componentSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfToExcelTool.vue'), 'utf8')

    expect(routerSource).toContain("path: '/tools'")
    expect(routerSource).toContain("component: () => import('@/views/ToolCenterView.vue')")
    expect(viewSource).toContain('<PdfToExcelTool')
    expect(componentSource).toContain('sharedToolsApi.convertPdfToExcel')
    expect(componentSource).toContain('文件仅用于本次转换')
  })
})
