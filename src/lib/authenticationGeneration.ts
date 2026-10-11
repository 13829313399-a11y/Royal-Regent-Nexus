// Session boundaries are independent of ordinary /auth/me snapshot ordering.
let generation = 0
export const getAuthenticationGeneration = () => generation
export const advanceAuthenticationGeneration = () => ++generation
export function announceSessionBoundary() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('auth-session-boundary-changed'))
}
