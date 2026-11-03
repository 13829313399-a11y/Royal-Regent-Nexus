import { beforeEach, expect, it } from 'vitest'
import { chooseWorkingVersion, readWorkingVersions, rememberWorkingVersion } from '../internalQuoteWorkingVersions'
import type { ApiInternalQuoteAlternative } from '@/api/internalQuote'

beforeEach(() => localStorage.clear())
const quote = { id: 'b-v2', documentQuoteId: 'doc', productRootId: 'p1', factoryId: 'huakang-b', status: 'drafting' }
it('persists per-product work choices across reads, separately by user, factory and document', () => {
  rememberWorkingVersion('u1', quote)
  rememberWorkingVersion('u1', { ...quote, id: 'p2-v3', productRootId: 'p2' })
  expect(readWorkingVersions('u1', 'huakang-b', 'doc')).toEqual({ lastQuoteId: 'p2-v3', lastRootId: 'p2', products: { p1: 'b-v2', p2: 'p2-v3' } })
  expect(readWorkingVersions('u2', 'huakang-b', 'doc').lastQuoteId).toBe('')
  expect(readWorkingVersions('u1', 'huaxing', 'doc').lastQuoteId).toBe('')
  expect(readWorkingVersions('u1', 'huakang-b', 'other').lastQuoteId).toBe('')
})
it('does not replace a work choice when an archived historical link is viewed', () => {
  rememberWorkingVersion('u1', quote)
  rememberWorkingVersion('u1', { ...quote, id: 'old', versionArchived: true })
  expect(readWorkingVersions('u1', 'huakang-b', 'doc').lastQuoteId).toBe('b-v2')
})
it('honors explicit current versions and group members without guessing the newest version', () => {
  const options = [{ quote_id: 'old' }, { quote_id: 'group' }, { quote_id: 'last' }, { quote_id: 'newest' }] as ApiInternalQuoteAlternative[]
  expect(chooseWorkingVersion(options, 'old', 'group', 'last', 'old')).toBe('old')
  expect(chooseWorkingVersion(options, 'other-product', 'group', 'last', 'old')).toBe('group')
  expect(chooseWorkingVersion(options, 'other-product', undefined, 'last', 'old')).toBe('last')
  expect(chooseWorkingVersion(options, 'other-product', 'deleted', 'last', 'old')).toBe('')
  expect(chooseWorkingVersion([{ quote_id: 'last', archived: true }, { quote_id: 'old' }] as ApiInternalQuoteAlternative[], '', undefined, 'last', 'old')).toBe('')
})
