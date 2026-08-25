import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const root = process.cwd()
const wizard = fs.readFileSync(path.join(root, 'src/features/injection-scheduling-v2/components/InjectionSchedulingImportWizard.vue'), 'utf8')
const api = fs.readFileSync(path.join(root, 'src/features/injection-scheduling-v2/api/injectionSchedulingV2Api.ts'), 'utf8')

describe('AI-B10/B11 workbook preview and mapping boundaries', () => {
  it('selects a workbook without an Artifact, scanner, or Pilot preflight', () => {
    expect(api).not.toContain("http.post('/ai/workbooks/inspect'")
    expect(wizard).not.toContain('uploadAIArtifact')
    expect(api).toContain("http.post('/ai/workbooks/mapping-proposal'")
    expect(wizard).toContain('选择后可直接生成预览')
    expect(wizard).toContain('无需额外确认，可直接生成预览')
  })

  it('keeps AI mappings in the existing human-reviewed profile draft flow', () => {
    expect(wizard).toContain('AI 建议仅供人工预览')
    expect(wizard).toContain('只能保存到现有 PROFILE_DRAFT，不能自动激活')
    expect(wizard).toContain('采用 AI 建议到人工草案')
    expect(wizard).toContain('保存映射草案')
    expect(wizard).toContain('提交导入模板审核')
    expect(wizard).toContain('mappingProposal.preview_manifest')
    expect(wizard).toContain('<PreviewCard')
  })

  it('offers AI layout fallback without a consent gate', () => {
    expect(api).toContain("body.set('recognition_mode', recognitionMode)")
    expect(api).not.toContain('cloud_ai_consent')
    expect(api).not.toContain('cloud_consent')
    expect(api).toContain("body.set('business_date', businessDate)")
    expect(wizard).toContain('固定模板优先，必要时 AI（推荐）')
    expect(wizard).toContain('直接使用 AI 识别布局')
    expect(wizard).not.toContain('有限工作簿结构')
    expect(wizard).toContain('AI 布局已通过后端来源校验')
    expect(wizard).toContain('确定性服务完成')
  })
})
