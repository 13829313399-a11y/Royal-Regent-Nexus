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

  it('registers an authenticated tool-center route and the unified document workspace', () => {
    const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
    const viewSource = readFileSync(join(process.cwd(), 'src/views/ToolCenterView.vue'), 'utf8')
    const workspaceSource = readFileSync(join(process.cwd(), 'src/features/document-studio/components/DocumentWorkspaceShell.vue'), 'utf8')
    const excelSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfToExcelTool.vue'), 'utf8')
    const wordSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfToWordTool.vue'), 'utf8')
    const splitSource = readFileSync(join(process.cwd(), 'src/components/tools/PdfSplitTool.vue'), 'utf8')
    const translationSource = readFileSync(join(process.cwd(), 'src/components/tools/DocumentTranslationTool.vue'), 'utf8')

    expect(routerSource).toContain("path: '/tools'")
    expect(routerSource).toContain("component: () => import('@/views/ToolCenterView.vue')")
    expect(viewSource).toContain('<DocumentToolTabs')
    expect(viewSource).toContain('<DocumentWorkspaceShell')
    expect(viewSource).toContain('<DocumentJobDrawer')
    expect(viewSource).toContain('智能文档工作台')
    expect(workspaceSource).toContain('sharedToolsApi.convertPdfToExcel')
    expect(workspaceSource).toContain('sharedToolsApi.convertPdfToWord')
    expect(workspaceSource).toContain('sharedToolsApi.splitPdf')
    expect(workspaceSource).toContain('<DocumentTranslationTool')
    expect(workspaceSource).toContain('createDocumentJob')
    expect(workspaceSource).toContain('不写入虚构任务历史')
    expect(excelSource).toContain('sharedToolsApi.convertPdfToExcel')
    expect(wordSource).toContain('sharedToolsApi.convertPdfToWord')
    expect(wordSource).toContain('文件仅用于本次转换')
    expect(splitSource).toContain('sharedToolsApi.splitPdf')
    expect(splitSource).toContain('按指定页段拆分')
    expect(translationSource).toContain('sharedToolsApi.translateDocument')
    expect(translationSource).toContain('选择需要翻译的工作表')
    expect(translationSource).toContain('未勾选的 Sheet 内容保持原样')
    expect(translationSource).toContain('版式、表格与线条')
    expect(translationSource).toContain('字体、字号与样式')
  })
})
