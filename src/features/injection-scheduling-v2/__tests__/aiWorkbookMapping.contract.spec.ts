import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const root = process.cwd()
const wizard = fs.readFileSync(path.join(root, 'src/features/injection-scheduling-v2/components/InjectionSchedulingImportWizard.vue'), 'utf8')
const api = fs.readFileSync(path.join(root, 'src/features/injection-scheduling-v2/api/injectionSchedulingV2Api.ts'), 'utf8')

describe('AI-B10/B11 workbook preview and mapping boundaries', () => {
  it('runs local inspection before import and discloses cloud snapshot use', () => {
    expect(api).toContain("http.post('/ai/workbooks/inspect'")
    expect(api).toContain("http.post('/ai/workbooks/mapping-proposal'")
    expect(wizard).toContain('本地只读语义检查通过')
    expect(wizard).toContain('原始 Excel 不发送')
    expect(wizard).toContain('不会创建 Import Batch、订单、Task 或 Profile')
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

  it('offers guarded AI layout fallback inside the existing import preview flow', () => {
    expect(api).toContain("body.set('recognition_mode', recognitionMode)")
    expect(api).toContain("body.set('cloud_ai_consent', cloudAiConsent ? 'true' : 'false')")
    expect(api).toContain("body.set('business_date', businessDate)")
    expect(wizard).toContain('固定模板优先，必要时 AI（推荐）')
    expect(wizard).toContain('直接使用 AI 识别布局')
    expect(wizard).toContain('有限工作簿结构')
    expect(wizard).toContain('AI 布局已通过后端来源校验')
    expect(wizard).toContain('确定性服务完成')
  })
})
