import type { DraftBucket, DraftDatabase } from '../draftPersistence'
const emptyDraftBucket = (): DraftBucket => ({ format: 1, drafts: {}, pending: null })
function copyDraft<T>(value: T): T {
  if (value == null || typeof value !== 'object' || value instanceof Blob) return value
  if (Array.isArray(value)) return value.map(copyDraft) as T
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, copyDraft(entry)])) as T
}
export const savedBuckets = new Map<string, DraftBucket>()
export const memoryDatabase: DraftDatabase = {
  async read(key) { return copyDraft(savedBuckets.get(key) ?? emptyDraftBucket()) },
  async update(key, change) {
    const current = copyDraft(savedBuckets.get(key) ?? emptyDraftBucket())
    change(current)
    savedBuckets.set(key, copyDraft(current))
    return copyDraft(current)
  },
}
