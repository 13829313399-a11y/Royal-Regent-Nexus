import {
  convertBuzzBeeP4InternalQuote,
  type BuzzBeeConversionResult,
} from './buzzbee'
import {
  parseP4InternalQuoteArtifact,
  type P4InternalQuoteArtifact,
} from './p4Artifact'

export type P4ConfiguredCustomerId = 'buzzbee' | 'disney' | 'dicky' | 'caixing'

export interface P4BuzzBeePreparedConversion {
  customerId: 'buzzbee'
  artifact: P4InternalQuoteArtifact
  result: BuzzBeeConversionResult
}

export type P4PreparedCustomerConversion = P4BuzzBeePreparedConversion

export class P4CustomerMappingError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'P4CustomerMappingError'
  }
}

function customerNameMatches(customerId: P4ConfiguredCustomerId, value: string) {
  const normalized = value.trim().toLowerCase().replace(/[\s_-]+/g, '')
  const accepted: Record<P4ConfiguredCustomerId, string[]> = {
    buzzbee: ['buzzbee'],
    disney: ['迪士尼', 'disney'],
    dicky: ['dickie', 'dicky'],
    caixing: ['彩星', 'caixing'],
  }
  return accepted[customerId].includes(normalized)
}

export function prepareP4CustomerConversion(
  buffer: ArrayBuffer,
  sourceFileName: string,
  customerId: P4ConfiguredCustomerId,
): P4PreparedCustomerConversion {
  const artifact = parseP4InternalQuoteArtifact(buffer)
  if (!customerNameMatches(customerId, artifact.customer)) {
    throw new P4CustomerMappingError(`受控文件客户“${artifact.customer || '未填写'}”与当前客户模板不一致`)
  }

  if (customerId === 'buzzbee') {
    return {
      customerId,
      artifact,
      result: convertBuzzBeeP4InternalQuote(artifact, sourceFileName),
    }
  }
  if (customerId === 'disney') {
    throw new P4CustomerMappingError(
      '迪士尼直转被阻断：标准 P4 尚未采集 Item Number、模号/穴数/每啤件数、Cycle Time、装饰工序及 3K/5K/10K MOQ 客户分档；请继续使用迪士尼专用内部报价 Excel。',
    )
  }
  if (customerId === 'dicky') {
    throw new P4CustomerMappingError(
      'Dickie 直转被阻断：客户模板依赖原“总表”的产品行、Mold #、英文翻译备注、付款/法规条款及单元格公式版式，标准 P4 不包含这些客户专属字段；请继续使用 Dickie 专用内部报价 Excel。',
    )
  }
  throw new P4CustomerMappingError(
    '彩星直转被阻断：标准 P4 尚未采集 Tool Plan 所需的 Cycle Time、每啤件数、客户模价/模具对应关系，以及塑胶/毛绒模板的客户专属分组字段；请继续使用对应的彩星专用内部报价 Excel。',
  )
}
