import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createDraftPersistence, copyDraft, restoreRecord, type DraftDatabase } from '../draftPersistence'
import type { Command } from '@/api/indonesiaMaterials'
import { memoryDatabase, savedBuckets } from './draftMemory'

const controllers: ReturnType<typeof createDraftPersistence>[] = []
async function open(database: DraftDatabase = memoryDatabase, key = 'user-a/huaxing') {
  const controller = createDraftPersistence(database); controllers.push(controller)
  controller.reset(key); await controller.load(); return controller
}
const command: Command = { factory_id: 'huaxing', operation_id: '00000000-0000-4000-8000-000000000001', action: 'customer_save', entity_id: null, expected_version: 0, data: { name: 'draft' } }
beforeEach(() => savedBuckets.clear())
afterEach(() => { controllers.splice(0).forEach(controller => controller.dispose()); vi.restoreAllMocks() })

describe('durable drafts and operation journal', () => {
  it('serializes rapid edits without dropping the final keystroke', async () => {
    const draft = await open()
    const outcomes = await Promise.all(['a', 'ab', 'abc', 'abcd'].map(text => draft.save('customer', { form: { name: text } })))
    expect(outcomes).toEqual([true, true, true, true])
    expect((await open()).bucket.value.drafts.customer?.state.form.name).toBe('abcd')
  })
  it('retains attachments without serializing File into an empty object', async () => {
    const draft = await open(), file = new File(['xlsx-content'], 'schedule.xlsx')
    await draft.save('import', { file, customer: 'CLIENT' })
    const reopened = await open()
    expect(reopened.bucket.value.drafts.import?.state.file).toBe(file)
    expect(copyDraft({ file }).file).toBe(file)
  })
  it('rejects an old tab overwriting or deleting a newer tab’s draft', async () => {
    const left = await open(); await left.save('customer', { form: { name: 'first' } })
    const oldRevision = left.bucket.value.drafts.customer!.revision
    const right = await open(); right.adopt('customer'); await right.save('customer', { form: { name: 'newer' } })
    await left.load() // even an invalidation must not adopt the other editor’s revision.
    expect(await left.save('customer', { form: { name: 'old tab' } })).toBe(false)
    expect(await left.remove('customer', oldRevision)).toBe(false)
    expect((await memoryDatabase.read('user-a/huaxing')).drafts.customer?.state.form.name).toBe('newer')
  })
  it('rejects an old tab recreating a draft deleted elsewhere', async () => {
    const left = await open(); await left.save('customer', { form: { name: 'first' } })
    const right = await open(); await right.remove('customer')
    expect(await left.save('customer', { form: { name: 'stale' } })).toBe(false)
    expect((await memoryDatabase.read('user-a/huaxing')).drafts.customer).toBeUndefined()
  })
  it('durably journals the exact operation before releasing it for HTTP and clears only its owner on success', async () => {
    const draft = await open()
    await draft.save('customer', { form: { name: 'customer input' } }); await draft.save('supply', { form: { purchase_no: 'other input' } })
    expect(await draft.begin(command, 'customer')).toBe(true)
    command.data.name = 'mutated after beginning'
    expect((await open()).bucket.value.pending?.command.data.name).toBe('draft')
    expect(await draft.finish(command.operation_id, true)).toBe(true)
    const reopened = await open()
    expect(reopened.bucket.value.pending).toBeNull()
    expect(reopened.bucket.value.drafts.customer).toBeUndefined()
    expect(reopened.bucket.value.drafts.supply).toBeDefined()
    command.data.name = 'draft'
  })
  it('keeps input after a definitive validation failure but releases the original journal', async () => {
    const draft = await open(); await draft.save('customer', { form: { name: 'retain me' } })
    await draft.begin(command, 'customer'); await draft.finish(command.operation_id, false)
    expect((await open()).bucket.value.drafts.customer?.state.form.name).toBe('retain me')
    expect(draft.bucket.value.pending).toBeNull()
  })
  it('does not bind another tab’s newer draft to an older submission', async () => {
    const left = await open(); await left.save('customer', { form: { name: 'A' } })
    const right = await open(); right.adopt('customer'); await right.save('customer', { form: { name: 'B' } })
    expect(await left.begin(command, 'customer')).toBe(false)
    expect((await memoryDatabase.read('user-a/huaxing')).pending).toBeNull()
    expect((await open()).bucket.value.drafts.customer?.state.form.name).toBe('B')
  })
  it('never recreates a finished replay journal or deletes a newer draft', async () => {
    const left = await open(); await left.save('customer', { form: { name: 'A' } }); await left.begin(command, 'customer')
    const right = await open(); await right.finish(command.operation_id, true); await right.save('customer', { form: { name: 'B' } })
    expect(await left.begin(command, 'customer', true)).toBe(false)
    expect(await left.finish(command.operation_id, true)).toBe(true)
    expect((await open()).bucket.value.drafts.customer?.state.form.name).toBe('B')
  })
  it('uses the selected recovery snapshot’s revision even if the cache refreshes during recovery', async () => {
    const left = await open(); await left.save('customer', { form: { name: 'A' } })
    const recovered = left.bucket.value.drafts.customer!
    const right = await open(); right.adopt('customer'); await right.save('customer', { form: { name: 'B' } })
    await left.load(); left.adopt('customer', recovered.revision)
    expect(await left.save('customer', { form: { name: 'A changed' } })).toBe(false)
  })
  it('keeps an absent revision after commit so a continuing import cannot overwrite another tab’s new draft', async () => {
    const left = await open(); await left.save('import', { customer: 'A' }); await left.begin(command, 'import'); await left.finish(command.operation_id, true)
    const right = await open(); await right.save('import', { customer: 'B' })
    await left.load()
    expect(await left.save('import', { customer: 'A continues' })).toBe(false)
    expect((await open()).bucket.value.drafts.import?.state.customer).toBe('B')
  })
  it('locks out competing commands and draft deletion while an operation is unresolved', async () => {
    const left = await open(); await left.save('customer', { form: { name: 'first' } }); await left.begin(command, 'customer')
    const right = await open()
    expect(await right.begin({ ...command, operation_id: 'different-operation' })).toBe(false)
    expect(await right.remove('customer')).toBe(false)
    expect(await right.save('customer', { form: { name: 'changed' } })).toBe(false)
    expect(right.bucket.value.pending?.command.operation_id).toBe(command.operation_id)
  })
  it('keeps the durable operation when clearing local storage fails after a server success', async () => {
    const database = { ...memoryDatabase, update: vi.fn(memoryDatabase.update) }
    const draft = await open(database); await draft.begin(command, 'customer')
    database.update.mockRejectedValueOnce(new Error('quota'))
    expect(await draft.finish(command.operation_id, true)).toBe(false)
    expect((await open()).bucket.value.pending?.command).toEqual(command)
    expect(draft.error.value).toContain('尚未安全保存')
  })
  it('does not publish an old account’s async read into a new account', async () => {
    let release!: (value: Awaited<ReturnType<DraftDatabase['read']>>) => void
    const draft = await open(); await draft.save('customer', { form: { name: 'private' } })
    const held = new Promise<Awaited<ReturnType<DraftDatabase['read']>>>(resolve => { release = resolve })
    const other = createDraftPersistence({ ...memoryDatabase, read: () => held }); controllers.push(other)
    other.reset('old'); const loading = other.load()
    other.reset('new'); release(await memoryDatabase.read('user-a/huaxing')); await loading
    expect(other.bucket.value.drafts).toEqual({}); expect(other.ready.value).toBe(false)
  })
  it('retains the original edit version and rejects unavailable or wrong-kind sources', () => {
    const row = { id: 'p', kind: 'product' as const, version: 9, data: {} }
    expect(restoreRecord([row], { id: 'p', kind: 'product', version: 3 }, 'product')?.version).toBe(3)
    expect(() => restoreRecord([row], { id: 'p', kind: 'customer', version: 3 }, 'product')).toThrow()
    expect(() => restoreRecord([], { id: 'p', kind: 'product', version: 3 }, 'product')).toThrow()
  })
})
