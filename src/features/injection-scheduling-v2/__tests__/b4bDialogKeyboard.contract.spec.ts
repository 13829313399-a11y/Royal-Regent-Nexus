import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentRoot = join(process.cwd(), 'src/features/injection-scheduling-v2/components')

describe('B4b dialog and menu source contracts', () => {
  it('requires every scheduling dialog to opt into the shared keyboard contract', () => {
    const components = [
      'AutoSchedulePreviewDialog.vue',
      'BacklogOrderCancelDialog.vue',
      'InjectionSchedulingExportDialog.vue',
      'InjectionSchedulingImportWizard.vue',
      'ManualAppendDialog.vue',
      'ManualDemandDialog.vue',
      'ManualMoveDialog.vue',
      'PublishPlanDialog.vue',
      'RevisionConflictDialog.vue',
      'WithdrawTaskDialog.vue',
    ]
    for (const component of components) {
      const source = readFileSync(join(componentRoot, component), 'utf8')
      expect(source, component).toContain('useDialogFocus')
      expect(source, component).toContain('dialog-live-announcement')
    }
  })

  it('connects the column menu trigger to the menu surface', () => {
    const viewSource = readFileSync(join(process.cwd(), 'src/features/injection-scheduling-v2/InjectionSchedulingV2View.vue'), 'utf8')
    expect(viewSource).toContain('aria-haspopup="menu"')
    expect(viewSource).toContain('aria-controls="column-preset-menu"')
  })
})
