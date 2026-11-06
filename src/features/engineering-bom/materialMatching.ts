import type { Material, Node } from './api'

export interface MatchSelection { row: number; key: string; material_id: string; material_version: number }
export interface MaterialMatch {
  row: number; key: string; code: string; name: string; unit: string; sourceAttribute: string
  material: Material | null; issue: string
}

export function materialMatches(nodes: Node[], materials: Material[]): MaterialMatch[] {
  return nodes.flatMap((node, index) => {
    if (node.material_id) return [] // A fixed historical version must never be silently replaced.
    const sourceAttribute = (node.source['物料属性'] || '').trim()
    const matches = materials.filter(m => m.code === node.source_code)
    const candidate = matches.length === 1 ? matches[0]! : null
    let issue = ''
    if (nodes.filter(n => n.key === node.key).length !== 1) issue = '用料行标识重复，请先修正'
    else if (!node.source_code || !node.source_name || !node.unit) issue = '缺少来源编码、名称或单位，请逐行选择'
    else if (!matches.length) issue = '未找到相同编码，请先建立并审核物料'
    else if (!candidate) issue = '编码存在多个候选，请先核对档案'
    else if (candidate.status !== 'ACTIVE' || candidate.data.engineering?.approval !== 'APPROVED') issue = '物料尚未审核或已停用'
    else if (candidate.name !== node.source_name) issue = '名称不同，请逐行核对'
    else if (candidate.data.unit !== node.unit) issue = '单位不同，不自动换算'
    else if (!['外购', '自制', '委外', '客供'].includes(candidate.data.engineering.attribute)) issue = '物料属性待核对'
    else if (sourceAttribute && sourceAttribute !== candidate.data.engineering.attribute) issue = '来源属性与档案不同，请逐行核对'
    return [{ row: index + 1, key: node.key, code: node.source_code, name: node.source_name, unit: node.unit,
      sourceAttribute, material: issue ? null : candidate, issue }]
  })
}

export function applyMaterialMatches(nodes: Node[], materials: Material[], selections: MatchSelection[]): Node[] {
  const candidates = materialMatches(nodes, materials)
  if (!selections.length || new Set(selections.map(s => s.row)).size !== selections.length) throw new Error('请选择独立用料行后再应用')
  const chosen = new Map<number, Material>()
  for (const selection of selections) {
    const candidate = candidates.find(c => c.row === selection.row && c.key === selection.key)?.material
    if (!candidate || candidate.id !== selection.material_id || candidate.version !== selection.material_version) {
      throw new Error('用料或候选物料已变化，请重新查看候选并勾选')
    }
    chosen.set(selection.row, candidate)
  }
  return nodes.map((node, index) => {
    const candidate = chosen.get(index + 1)
    return candidate ? { ...node, material_id: candidate.id, material_version: candidate.version } : node
  })
}
