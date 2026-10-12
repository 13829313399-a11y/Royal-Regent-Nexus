import { shallowReactive } from 'vue'
import type { ContextSelection } from './v2'

// Pages expose identifiers and filters only; the server re-reads authorized facts.
const providers = shallowReactive(new Map<string, () => ContextSelection | null>())
export function registerAssistantSelection(module: string, read: () => ContextSelection | null) {
  providers.set(module, read)
  return () => { if (providers.get(module) === read) providers.delete(module) }
}
export function assistantSelection(module?: string) { return module ? providers.get(module)?.() ?? null : null }
