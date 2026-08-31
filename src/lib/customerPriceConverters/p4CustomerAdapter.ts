import { convertYinhuiP4InternalQuote, type YinhuiConversionResult } from './yinhui'
import { extractYinhuiProductImage } from './yinhuiTemplate'
import {
  convertBuzzBeeP4InternalQuote,
  type BuzzBeeConversionResult,
} from './buzzbee'
import {
  convertDisneyP4InternalQuote,
  type DisneyConversionResult,
} from './disney'
import {
  convertDickyP4InternalQuote,
  type DickyConversionResult,
} from './dicky'
import {
  convertCaixingP4InternalQuote,
  type CaixingConversionResult,
} from './caixing'
import {
  convertThreeSixtyP4InternalQuote,
  type ThreeSixtyConversionResult,
} from './threeSixty'
import {
  parseP4InternalQuoteArtifact,
  type P4ArtifactMetadata,
  type P4InternalQuoteArtifact,
} from './p4Artifact'

export type P4ConfiguredCustomerId = 'buzzbee' | 'disney' | 'dicky' | 'caixing' | 'three-sixty' | 'yinhui'

export interface P4BuzzBeePreparedConversion {
  customerId: 'buzzbee'
  artifact: P4InternalQuoteArtifact
  result: BuzzBeeConversionResult
}

export interface P4DisneyPreparedConversion {
  customerId: 'disney'
  artifact: P4InternalQuoteArtifact
  result: DisneyConversionResult
}

export interface P4DickyPreparedConversion {
  customerId: 'dicky'
  artifact: P4InternalQuoteArtifact
  result: DickyConversionResult
}

export interface P4CaixingPreparedConversion {
  customerId: 'caixing'
  artifact: P4InternalQuoteArtifact
  result: CaixingConversionResult
}

export interface P4ThreeSixtyPreparedConversion {
  customerId: 'three-sixty'
  artifact: P4InternalQuoteArtifact
  result: ThreeSixtyConversionResult
}

export interface P4YinhuiPreparedConversion {
  customerId: 'yinhui'
  artifact: P4InternalQuoteArtifact
  result: YinhuiConversionResult
}

export type P4PreparedCustomerConversion = P4YinhuiPreparedConversion | P4BuzzBeePreparedConversion | P4DisneyPreparedConversion | P4DickyPreparedConversion | P4CaixingPreparedConversion | P4ThreeSixtyPreparedConversion

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
    yinhui: ['银辉', '銀輝', '银辉客', '銀輝客', 'yinhui', 'silverlit'],
    disney: ['迪士尼', 'disney'],
    dicky: ['dickie', 'dicky'],
    caixing: ['彩星', 'caixing'],
    'three-sixty': ['360', 'threesixty'],
  }
  return accepted[customerId].includes(normalized)
}

export function prepareP4CustomerConversion(
  buffer: ArrayBuffer,
  sourceFileName: string,
  customerId: P4ConfiguredCustomerId,
  handoffMetadata: P4ArtifactMetadata = {},
): P4PreparedCustomerConversion {
  const artifact = parseP4InternalQuoteArtifact(buffer, handoffMetadata)
  if (!customerNameMatches(customerId, artifact.customer)) {
    throw new P4CustomerMappingError(`受控文件客户“${artifact.customer || '未填写'}”与当前客户模板不一致`)
  }

  if (customerId === 'yinhui') {
    const result = convertYinhuiP4InternalQuote(artifact, sourceFileName)
    result.quoteData.image = extractYinhuiProductImage(buffer, '报价明细')
    return { customerId, artifact, result }
  }
  if (customerId === 'buzzbee') {
    return {
      customerId,
      artifact,
      result: convertBuzzBeeP4InternalQuote(artifact, sourceFileName),
    }
  }
  if (customerId === 'disney') {
    try {
      return {
        customerId,
        artifact,
        result: convertDisneyP4InternalQuote(artifact, sourceFileName),
      }
    } catch (error) {
      if (error instanceof P4CustomerMappingError) throw error
      throw new P4CustomerMappingError(error instanceof Error ? error.message : '迪士尼 P4 映射失败')
    }
  }
  if (customerId === 'dicky') {
    try {
      return {
        customerId,
        artifact,
        result: convertDickyP4InternalQuote(artifact, sourceFileName),
      }
    } catch (error) {
      if (error instanceof P4CustomerMappingError) throw error
      throw new P4CustomerMappingError(error instanceof Error ? error.message : 'Dickie P4 映射失败')
    }
  }
  if (customerId === 'three-sixty') {
    try {
      return {
        customerId,
        artifact,
        result: convertThreeSixtyP4InternalQuote(artifact, sourceFileName),
      }
    } catch (error) {
      if (error instanceof P4CustomerMappingError) throw error
      throw new P4CustomerMappingError(error instanceof Error ? error.message : '360 P4 映射失败')
    }
  }
  try {
    return {
      customerId: 'caixing',
      artifact,
      result: convertCaixingP4InternalQuote(artifact, sourceFileName),
    }
  } catch (error) {
    if (error instanceof P4CustomerMappingError) throw error
    throw new P4CustomerMappingError(error instanceof Error ? error.message : '彩星 P4 映射失败')
  }
}
