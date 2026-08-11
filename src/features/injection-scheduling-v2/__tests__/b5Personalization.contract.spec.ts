import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const featureRoot = join(process.cwd(), 'src/features/injection-scheduling-v2')
const preferencesSource = readFileSync(join(featureRoot, 'config/schedulingPreferences.ts'), 'utf8')
const viewSource = readFileSync(join(featureRoot, 'InjectionSchedulingV2View.vue'), 'utf8')
const menuSource = readFileSync(join(featureRoot, 'components/ColumnPresetMenu.vue'), 'utf8')
const machineSource = readFileSync(join(featureRoot, 'MachineDatabaseView.vue'), 'utf8')
const moldSource = readFileSync(join(featureRoot, 'SharedMoldDatabaseView.vue'), 'utf8')
const auxiliaryCss = readFileSync(join(featureRoot, 'shared-mold-database.css'), 'utf8')

describe('B5 personalization contracts', () => {
  it('keeps browser preferences versioned and scoped by authenticated user and factory', () => {
    expect(preferencesSource).toContain("rr:injection-scheduling:layout:v1")
    expect(preferencesSource).toContain('userId')
    expect(preferencesSource).toContain('factoryId')
    expect(preferencesSource).toContain('version: schedulingPreferencesVersion')
  })

  it('does not introduce API, schema or server synchronization for layout preferences', () => {
    expect(preferencesSource).not.toMatch(/from ['"].*api/)
    expect(preferencesSource).not.toContain('axios')
    expect(preferencesSource).not.toContain('fetch(')
    expect(menuSource).toContain('仅保存在当前浏览器，不跨设备同步')
  })

  it('connects visible density, custom presets and frozen columns to the existing grid', () => {
    expect(viewSource).toContain(':density="store.density"')
    expect(viewSource).toContain('@density="store.setDensity"')
    expect(viewSource).toContain('@toggle-freeze="store.toggleFrozenColumn"')
    expect(viewSource).toContain('@save-custom-preset="store.saveCustomPreset"')
    expect(menuSource).toContain("density: [value: SchedulingDensityMode]")
    expect(menuSource).toContain("toggleFreeze: [key: string]")
  })

  it('uses one auxiliary-page visual shell for the machine and shared-mold databases', () => {
    expect(machineSource).toContain('scheduling-auxiliary-page')
    expect(moldSource).toContain('scheduling-auxiliary-page')
    expect(auxiliaryCss).toContain('.scheduling-auxiliary-page')
  })
})
