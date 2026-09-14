import { shanghaiDateTimeString } from './businessTime'

/** The live workspace may show only an API-confirmed freshness timestamp. */
export function workspaceFreshnessLabel(isPreview: boolean, sampleAsOf: string, liveAsOf: string | null): string {
  if (isPreview) return shanghaiDateTimeString(sampleAsOf)
  return liveAsOf ? shanghaiDateTimeString(liveAsOf) : '尚未读取'
}
