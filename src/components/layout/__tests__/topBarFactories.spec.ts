import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const topBarSource = readFileSync(join(process.cwd(), 'src/components/layout/TopBar.vue'), 'utf8')
const factorySource = readFileSync(join(process.cwd(), 'src/data/enterpriseMock.ts'), 'utf8')
const appStoreSource = readFileSync(join(process.cwd(), 'src/stores/app.ts'), 'utf8')

describe('TopBar factory switcher source contract', () => {
  it('includes Huakang C and D without squeezing the header controls', () => {
    expect(factorySource).toContain("'huakang-c'")
    expect(factorySource).toContain("'huakang-d'")
    expect(factorySource).toContain("name: '华康C'")
    expect(factorySource).toContain("name: '华康D'")
    expect(topBarSource).toContain('max-w-[40vw]')
    expect(topBarSource).toContain('overflow-x-auto')
    expect(topBarSource).toContain('min-w-max')
    expect(topBarSource).toContain('shrink-0')
    expect(topBarSource).toContain(':aria-label="`切换至${getTopBarFactoryLabel(factory)}`"')
  })

  it('keeps factory scopes that have no production dataset out of production modules', () => {
    expect(appStoreSource).toContain('productionFactoryContextIds.includes')
    expect(factorySource).toContain("Exclude<FactoryContextId, 'group' | 'huakang-c' | 'huakang-d'>")
  })
})
