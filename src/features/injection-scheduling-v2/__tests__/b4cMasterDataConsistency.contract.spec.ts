import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const featureRoot = join(process.cwd(), 'src/features/injection-scheduling-v2')
const moldSource = readFileSync(join(featureRoot, 'SharedMoldDatabaseView.vue'), 'utf8')
const machineSource = readFileSync(join(featureRoot, 'MachineDatabaseView.vue'), 'utf8')
const sharedStyles = readFileSync(join(featureRoot, 'shared-mold-database.css'), 'utf8')
const machineStyles = readFileSync(join(featureRoot, 'machine-database.css'), 'utf8')

describe('B4c master-data consistency contracts', () => {
  it('uses the selected factory and centralized machine status wording', () => {
    expect(moldSource).not.toContain('华兴机安能力')
    expect(moldSource).toContain("{{ factoryNames[factoryId] }}机安能力")
    expect(machineSource).toContain('machineStatusMeta(machine.status).label')
  })

  it('removes 8-10px text and raw rN revisions from the default surfaces', () => {
    expect(sharedStyles).not.toMatch(/font-size:\s*(?:8|9|10)px/)
    expect(machineStyles).not.toMatch(/font-size:\s*(?:8|9|10)px/)
    expect(moldSource).not.toMatch(/r\{\{\s*(?:item|detail)\.revision/)
    expect(machineSource).not.toMatch(/r\{\{\s*machine\.revision/)
    expect(moldSource).toContain('资料版本')
    expect(machineSource).toContain('资料版本')
  })

  it('loads direct-route motion styles and gives every drawer an explicit focus contract', () => {
    for (const source of [moldSource, machineSource]) {
      expect(source).toContain("import './styles/motion.css'")
      expect(source).toContain('useDialogFocus')
      expect(source).toContain('role="dialog"')
      expect(source).toContain('aria-modal="true"')
      expect(source).toContain('aria-labelledby=')
    }
    expect(moldSource.match(/useDialogFocus\(/g)).toHaveLength(2)
    expect(machineSource.match(/useDialogFocus\(/g)).toHaveLength(1)
  })
})
