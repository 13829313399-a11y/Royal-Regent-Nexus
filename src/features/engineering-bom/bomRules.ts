import { emptyBom, newNode, type Bom, type BomData, type Material, type Node } from './api'

export type FinishedProcess = '手工' | '车缝'

/** Only fresh BOMs receive a scaffold; saved/imported occurrence identities remain intact. */
export function newStructuredBom(process: FinishedProcess): BomData {
  const data = emptyBom(), root = data.nodes[0]!
  root.process = process
  if (process === '手工') data.nodes.push({ ...newNode(), parent: root.key, process: '车缝' })
  return data
}

export function nodeAttribute(node: Node, bom: Bom | null, catalog: Material[]): string {
  if (!node.material_id) return node.source['物料属性']?.trim() || ''
  const material = bom?.materials[`${node.material_id}:${node.material_version}`]
    || catalog.find(m => m.id === node.material_id && m.version === node.material_version)
  return material?.data.engineering?.attribute || ''
}
