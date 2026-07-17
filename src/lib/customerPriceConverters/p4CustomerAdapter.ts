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
  parseP4InternalQuoteArtifact,
  type P4InternalQuoteArtifact,
} from './p4Artifact'

export type P4ConfiguredCustomerId = 'buzzbee' | 'disney' | 'dicky' | 'caixing'

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

export type P4PreparedCustomerConversion = P4BuzzBeePreparedConversion | P4DisneyPreparedConversion | P4DickyPreparedConversion | P4CaixingPreparedConversion

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
