import type { EntryOrigin } from './navigation'

export interface HistoryPoint { position: number | null; current: string | null; back: string | null; forward: string | null }
export function historyPoint(): HistoryPoint {
  const state = window.history.state
  return { position: Number.isSafeInteger(state?.position) ? state.position : null,
    current: state?.current ?? null, back: state?.back ?? null, forward: state?.forward ?? null }
}

/** A confirmed direct home-to-workspace history edge. */
export interface ReturnEntry {
  origin: EntryOrigin
  moduleId: string
  modulePath: string
  position: number | null
  adjacent: boolean
  time: number
}

export function rememberEntry(origin: EntryOrigin, moduleId: string, modulePath: string, point: HistoryPoint, time: number): ReturnEntry {
  const adjacent = origin.historyPosition !== null && point.position === origin.historyPosition + 1
    && point.current === modulePath && point.back === origin.homePath
  return { origin, moduleId, modulePath, position: point.position, adjacent, time }
}

export function matchReturn(entry: ReturnEntry | null, moduleId: string, modulePath: string, homeId: string, homePath: string,
  context: string, point: HistoryPoint, strict: boolean, now: number) {
  if (!entry || entry.moduleId !== moduleId || entry.origin.expectedId !== moduleId
    || entry.origin.context !== context || entry.origin.homeId !== homeId) return undefined
  if (strict && (!entry.adjacent || entry.modulePath !== modulePath || entry.origin.homePath !== homePath || point.position !== entry.origin.historyPosition
    || point.current !== homePath || point.forward !== modulePath || now < entry.time || now - entry.time > 30 * 60_000)) return undefined
  return entry.origin
}
