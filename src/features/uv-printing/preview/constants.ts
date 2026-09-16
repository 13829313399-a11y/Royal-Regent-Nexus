import type { BusinessDate, IsoInstant, UvFactoryId } from '../contracts'
import { shanghaiInstant } from '../domain/businessTime'

/**
 * 样例的固定基准值（轻量模块）。
 *
 * 这些常量被工作区上下文与样例 transport 共用，但如果它们定义在 `fixtures.ts`
 * 里，任何静态引用都会把整套合成记录拖进生产包。因此基准值单独放在这里，
 * `fixtures.ts` 从这里导入并原样复用，生产构建里不会出现 DEMO- 业务记录。
 */

export const SAMPLE_FACTORY_ID: UvFactoryId = 'huakang-a'
export const SAMPLE_BUSINESS_DATE: BusinessDate = '2026-09-13'
export const SAMPLE_TODAY = SAMPLE_BUSINESS_DATE
export const SAMPLE_MONTH = '2026-09'
/** 样例币种：规格 5.4 标注为【待确认】，此处只用于样例，旧历史不猜币种。 */
export const SAMPLE_CURRENCY = 'HKD'
export const SAMPLE_AS_OF: IsoInstant = shanghaiInstant(SAMPLE_BUSINESS_DATE, '14:20')
export const SAMPLE_DEMO_TAG = 'DEMO-'
