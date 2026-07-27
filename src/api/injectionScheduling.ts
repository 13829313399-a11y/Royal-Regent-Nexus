import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import type { ScheduleMoveRequest, SchedulingSnapshot } from '@/types/injectionScheduling'

/**
 * Front-end integration seam only. No request is issued in the current preview.
 * A future backend can implement this contract without changing the page components.
 */
export interface InjectionSchedulingRepository {
  loadSnapshot(factoryId: ProductionFactoryContextId): Promise<SchedulingSnapshot | null>
  validateMove(request: ScheduleMoveRequest): Promise<{ allowed: boolean; reasons: string[] }>
  publishVersion(version: string): Promise<{ version: string; publishedAt: string }>
}

export const injectionSchedulingEndpointDraft = {
  snapshot: '/api/injection-scheduling/snapshot',
  validateMove: '/api/injection-scheduling/moves/validate',
  versions: '/api/injection-scheduling/versions',
} as const

