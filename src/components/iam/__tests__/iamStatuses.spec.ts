import { expect, it } from 'vitest'
import {
  personStatusPresentation,
  assignmentStatusPresentation,
  changeStatusPresentation,
  handoverStatusPresentation,
} from '../workspace/iam-status'
import {
  knownIdentityMode,
  rememberIdentityMode,
  setIdentityViewer,
} from '../workspace/identity-ui-context'
it('keeps pending meanings separate for people and handovers', () => {
  expect(personStatusPresentation('pending').label).toBe('待审核')
  expect(handoverStatusPresentation('pending').label).toBe('待接管')
  expect(changeStatusPresentation('scheduled').label).toBe('已预约')
  expect(assignmentStatusPresentation('scheduled').label).toBe('未来生效')
})
it('trusts only previously authorized context and clears it when the viewer changes', () => {
  setIdentityViewer('a')
  expect(knownIdentityMode('a', 'target')).toBe('unknown')
  rememberIdentityMode('a', 'target', 'v2')
  expect(knownIdentityMode('a', 'target')).toBe('v2')
  setIdentityViewer('')
  expect(knownIdentityMode('a', 'target')).toBe('unknown')
})
