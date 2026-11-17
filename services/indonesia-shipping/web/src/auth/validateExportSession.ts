import { api } from '../api/client'
import { getSessionGeneration, getStoredSession, saveSession, invalidateNexusSession, sessionFingerprint, type AuthSession } from './permissions'
import { nexusBase } from '../deployment'

// Some original exports are generated entirely from cached rows in the browser.
// Check their owner again before allowing the original export handler to run.
export async function validateExportSession(expectedGeneration = getSessionGeneration()) {
  if (!nexusBase()) return true
  const owner = getStoredSession()
  const generation = getSessionGeneration()
  if (!owner || generation !== expectedGeneration) return false
  try {
    const { data } = await api.get<AuthSession>('/session', { timeout: 15000 })
    if (generation !== getSessionGeneration()) return false
    if (sessionFingerprint(owner) !== sessionFingerprint(data)) {
      invalidateNexusSession()
      return false
    }
    saveSession(data)
    return true
  } catch { if (generation === getSessionGeneration()) invalidateNexusSession(); return false }
}
