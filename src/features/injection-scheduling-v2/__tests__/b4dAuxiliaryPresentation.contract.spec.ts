import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const source = (file: string) => readFileSync(join(root, 'components', file), 'utf8')

describe('B4d auxiliary workflow presentation contracts', () => {
  it('moves import governance and batch diagnostics behind business labels and technical details', () => {
    const wizard = source('InjectionSchedulingImportWizard.vue')
    expect(wizard).toContain('importBatchStateMeta')
    expect(wizard).toContain('importDocumentKindMeta')
    expect(wizard).toContain('masterDataEntityMeta')
    expect(wizard).toContain('profileStatusMeta')
    expect(wizard).toContain('SchedulingTechnicalDetails')
    expect(wizard).not.toContain('const stateLabel')
    expect(wizard).not.toContain('generation {{ batch.previewGeneration }} · r{{ batch.revision }}')
    expect(wizard).not.toContain('只进入 DRAFT / BACKLOG')
  })

  it('keeps export raw bindings and versions out of the default snapshot', () => {
    const dialog = source('InjectionSchedulingExportDialog.vue')
    expect(dialog).toContain('planStatusMeta(plan.status).label')
    expect(dialog).toContain('exportBindingSourceMeta')
    expect(dialog).toContain('SchedulingTechnicalDetails')
    expect(dialog).not.toContain('{{ plan.status }} · r{{ plan.revision }}')
    expect(dialog).not.toContain('IMPORT_PROFILE binding')
    expect(dialog).not.toContain('system_standard_v1</em>')
    expect(dialog).not.toContain('veryHidden')
  })

  it('uses the shared presentation catalog across manual and eligibility surfaces', () => {
    const append = source('ManualAppendDialog.vue')
    const withdraw = source('WithdrawTaskDialog.vue')
    const demand = source('ManualDemandDialog.vue')
    const eligibility = source('EligibilityChecks.vue')

    expect(append).toContain('fitDecisionMeta(preview.decision).label')
    expect(append).toContain('SchedulingTechnicalDetails')
    expect(append).not.toContain('{{ preview.decision }}')
    expect(append).not.toContain('planning DRAFT')
    expect(withdraw).toContain('planStatusMeta')
    expect(withdraw).toContain('SchedulingTechnicalDetails')
    expect(demand).toContain('priorityMeta(value).label')
    expect(demand).toContain('materialReadinessMeta(value).label')
    expect(demand).toContain('factoryMeta(props.factoryId).label')
    expect(eligibility).toContain('fitDecisionMeta')
    expect(eligibility).toContain('machineStatusMeta')
  })

  it('maps operations states centrally and collapses raw diagnostics', () => {
    const dashboard = source('Phase5OperationsDashboard.vue')
    expect(dashboard).toContain('integrationStatusMeta')
    expect(dashboard).toContain('speedModelStatusMeta')
    expect(dashboard).toContain('SchedulingTechnicalDetails')
    expect(dashboard).not.toContain("integration.sourceKey || 'default'")
    expect(dashboard).not.toContain('analytics[card.key].formula')
  })
})
