import { http } from '@/lib/http'

export type IssuePhotoReference = 'contract' | 'customer_po' | 'po'

export interface IssuePhotoRow {
  contract_no: string
  reference_kind?: IssuePhotoReference
  customer_po?: string
  item_no: string
  requested_quantity: string
  evidence: string
  top: number
  bottom: number
}

export interface IssuePhotoResult {
  document_no: string
  rotation: number
  rows: IssuePhotoRow[]
  has_header?: boolean
}

export interface IssuePhotoStock {
  id: string
  poNumber: string
  customerPo?: string
  itemNo: string
  balance: number
}

export interface IssuePhotoDraft {
  documentNo: string
  positions: string[]
  requested: Record<string, string>
}

export async function readIssuePhoto(factory: string, file: File, signal: AbortSignal) {
  const form = new FormData()
  form.append('factory_id', factory)
  form.append('file', file)
  const { data } = await http.post<IssuePhotoResult>('/carton-procurement/inventory/issue-photo', form, {
    headers: { 'Content-Type': 'multipart/form-data' }, signal, timeout: 55_000,
  })
  return data
}

const normalize = (value: string) => value.normalize('NFKC').toUpperCase().replace(/[—–]/g, '-').replace(/\s/g, '')
const similar = (value: string) => value.replace(/(?<=\d)\.(?=\d)/g, '').replace(/[IL]/g, '1').replace(/O/g, '0')
const compact = (value: string) => similar(value).replace(/[-._/]/g, '')

function oneCharacterApart(first: string, second: string) {
  if (first === second || Math.abs(first.length - second.length) > 1) return false
  const [short, long] = first.length <= second.length ? [first, second] : [second, first]
  let index = 0
  while (index < short.length && short[index] === long[index]) index++
  return short.slice(index + Number(short.length === long.length)) === long.slice(index + 1)
}

export function issuePhotoMatches<T extends IssuePhotoStock>(
  row: Pick<IssuePhotoRow, 'contract_no' | 'reference_kind' | 'customer_po' | 'item_no' | 'evidence'>,
  positions: T[],
  previousContract = '',
  previousItem = '',
  manual = false,
) {
  const reference = normalize(row.contract_no)
  const extraPo = normalize(row.customer_po ?? '')
  const item = normalize(row.item_no)
  const previous = normalize(previousContract)
  const kind = row.reference_kind ?? 'contract'
  const suffix = kind === 'contract' && /^-\d+$/.test(reference)
  const inherited = suffix && previous ? previous.replace(/-\d+$/, '') + reference : ''
  const evidence = normalize(row.evidence)
  const evidenceTokens = new Set(row.evidence.split(/[\s·]+/).map(value => compact(normalize(value))).filter(Boolean))
  const ranked = positions.flatMap(position => {
    if (position.balance <= 0) return []
    const contract = normalize(position.poNumber)
    const customerPo = normalize(position.customerPo ?? '')
    const extraPoExact = !!extraPo && customerPo === extraPo
    const references = [kind === 'customer_po' ? '' : contract, kind === 'contract' ? '' : customerPo].filter(Boolean)
    const referenceExact = !!reference && references.includes(reference)
    const code = normalize(position.itemNo)
    const itemExact = !!item && code === item
    const inferred = !!inherited && contract === inherited
    const itemInherited = inferred && !item && !!previousItem && code === normalize(previousItem)
    const approximatePair = references.some(source => source.length >= 5 && code.length >= 4 && (
      (reference.length >= 5 && item.length >= 4 && compact(source) === compact(reference) && compact(code) === compact(item))
      || (referenceExact && item.length >= 5 && oneCharacterApart(compact(code), compact(item)))
      || (itemExact && reference.length >= 5 && oneCharacterApart(compact(source), compact(reference)))
      || (evidenceTokens.has(compact(source)) && evidenceTokens.has(compact(code)))
      || [source + code, code + source].some(joined => compact(evidence).includes(compact(joined)))
    ))
    const matchedFields = [
      kind !== 'customer_po' && contract === reference ? '合同' : '',
      kind !== 'contract' && customerPo === reference ? '客户 PO' : '',
    ].filter(Boolean).join('、')
    const match = (score: number, label: string) => [{ position, score, label }]
    if (extraPoExact && itemExact && (referenceExact || !reference)) {
      return match(7, referenceExact ? '合同、客户 PO 和货号匹配' : '客户 PO 和货号匹配')
    }
    if (referenceExact && itemExact) {
      const pair = matchedFields.endsWith('PO') ? `${matchedFields} 和货号匹配` : '合同和货号匹配'
      return match(6, extraPo ? `${pair}，客户 PO 待核对` : pair)
    }
    if (inferred && (itemExact || itemInherited)) return match(5, '按上行合同推测，待核对')
    if (approximatePair) return match(4, '从近似或连写字段匹配，待核对')
    if (inferred) return match(3, '按上行合同推测，待核对货号')
    if (referenceExact) return match(2, item ? `按${matchedFields}匹配，货号不同，待核对` : `按${matchedFields}匹配`)
    if (extraPoExact) return match(2, '按客户 PO 匹配，待核对合同和货号')
    if (itemExact) return match(2, reference ? '仅货号匹配，编号待核对' : '按货号匹配')
    if (code.length >= 5 && evidenceTokens.has(compact(code))) return match(1, '原图中找到货号，待核对合同')
    if (references.some(source => source.length >= 6 && evidenceTokens.has(compact(source)))) {
      return match(1, '原图中找到合同或 PO，待核对货号')
    }
    if (manual) {
      const partialReference = reference.length >= 4 && references.some(source => source.includes(reference))
      const partialItem = item.length >= 4 && code.includes(item)
      if (partialReference || partialItem) {
        return match(Number(partialReference) + Number(partialItem), '按输入的编号片段查找，待核对')
      }
    }
    return []
  }).sort((a, b) => b.score - a.score)
  const best = ranked[0]?.score ?? 0
  return ranked.filter(result => result.score === best)
}
