export type DeploymentNotice = {
  id: string
  phase: 'scheduled' | 'maintenance' | 'completed' | 'cancelled'
  message: string
  startsAt: number
  expiresAt?: number
}

export function parseDeploymentNotice(value: unknown): DeploymentNotice | null {
  if (!value || typeof value !== 'object') return null
  const data = value as Record<string, unknown>
  const phases = ['scheduled', 'maintenance', 'completed', 'cancelled']
  if (typeof data.id !== 'string' || !/^[a-f0-9]{32}$/.test(data.id)
    || !phases.includes(String(data.phase)) || typeof data.message !== 'string' || data.message.length > 300) return null
  const startsAt = Date.parse(String(data.starts_at))
  const expiresAt = data.expires_at ? Date.parse(String(data.expires_at)) : undefined
  if (!Number.isFinite(startsAt) || (expiresAt !== undefined && !Number.isFinite(expiresAt))) return null
  if (['completed', 'cancelled'].includes(String(data.phase)) && expiresAt === undefined) return null
  return { id: data.id, phase: data.phase as DeploymentNotice['phase'], message: data.message, startsAt, expiresAt }
}

export function countdownText(seconds: number): string {
  const remaining = Math.max(0, Math.ceil(seconds))
  return `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}`
}
