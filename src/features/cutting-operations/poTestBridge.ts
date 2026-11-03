/** Explicit opt-in for a database-copy acceptance build; never grants permissions. */
export function isCuttingPoTestBridgeEnabled(): boolean {
  return import.meta.env.VITE_CUTTING_PO_TEST_BRIDGE === 'true'
    && Boolean(import.meta.env.VITE_CUTTING_ACCEPTANCE_RELEASE?.trim())
}
