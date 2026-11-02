import { strFromU8, unzipSync } from 'fflate'
export interface H360Image { bytes: Uint8Array; extension: 'png' | 'jpeg'; width: number; height: number }
const parse = (xml: string) => new DOMParser().parseFromString(xml, 'application/xml')
const resolve = (base: string, target: string) => {
  const parts = (target.startsWith('/') ? target.slice(1) : `${base.slice(0, base.lastIndexOf('/') + 1)}${target}`).split('/')
  const result: string[] = []; for (const part of parts) { if (part === '..') result.pop(); else if (part && part !== '.') result.push(part) }
  return result.join('/')
}
const relPath = (path: string) => `${path.slice(0, path.lastIndexOf('/') + 1)}_rels/${path.slice(path.lastIndexOf('/') + 1)}.rels`

function imagePixels(bytes: Uint8Array, extension: 'png' | 'jpeg') {
  const u16 = (i: number) => bytes[i]! * 256 + bytes[i + 1]!
  if (extension === 'png' && bytes.length >= 24 && bytes[0] === 137 && bytes[1] === 80) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    const width = view.getUint32(16), height = view.getUint32(20)
    if (width > 0 && height > 0) return { width, height }
  }
  if (extension === 'jpeg' && bytes[0] === 255 && bytes[1] === 216) {
    let i = 2
    while (i + 8 < bytes.length) {
      if (bytes[i] !== 255) { i++; continue }
      const marker = bytes[i + 1]!; i += 2
      if (marker === 217 || marker === 218) break
      if (marker === 255) { i--; continue }
      if (marker === 1 || (marker >= 208 && marker <= 216)) continue
      const length = u16(i)
      if (length < 2 || i + length > bytes.length) break
      if ([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207].includes(marker) && length >= 8) {
        const height = u16(i + 3), width = u16(i + 5)
        if (width > 0 && height > 0) return { width, height }
      }
      i += length
    }
  }
}

/** Resolve only the selected sheet's relationships. Never copy source XML or arbitrary media. */
export function readHuaxing360SourceExtras(buffer: ArrayBuffer, sheetName: string) {
  const zip = unzipSync(new Uint8Array(buffer)); const xml = (path: string) => zip[path] ? strFromU8(zip[path]) : ''
  const relationship = (path: string, id: string) => Array.from(parse(xml(relPath(path))).getElementsByTagName('Relationship')).find(r => r.getAttribute('Id') === id && r.getAttribute('TargetMode') !== 'External')?.getAttribute('Target')
  const sheet = Array.from(parse(xml('xl/workbook.xml')).getElementsByTagName('sheet')).find(s => s.getAttribute('name') === sheetName)
  const target = relationship('xl/workbook.xml', sheet?.getAttribute('r:id') ?? '')
  if (!target) return { formulas: {}, image: undefined, notice: '当前内部页关系缺失，未提取产品图片' }
  const path = resolve('xl/workbook.xml', target)
  const sourceXml = xml(path).replace(/<c\b[^>]*\/>/g, '').replace(/<row\b[^>]*>\s*<\/row>/g, '')
  const doc = parse(sourceXml); const formulas: Record<string, string> = {}; const shared = new Map<string, string>()
  for (const cell of Array.from(doc.getElementsByTagName('c'))) {
    const f = cell.getElementsByTagName('f')[0]; if (f?.textContent && f.getAttribute('t') === 'shared') shared.set(f.getAttribute('si') ?? '', f.textContent)
  }
  for (const cell of Array.from(doc.getElementsByTagName('c'))) {
    const f = cell.getElementsByTagName('f')[0]; if (!f) continue
    const master = shared.get(f.getAttribute('si') ?? '') ?? ''
    // Fee allocation constants have no relative addresses, so their shared formula is identical.
    formulas[cell.getAttribute('r') ?? ''] = f.textContent || (/^[\d.\s()+*/-]+$/.test(master) ? master : '#SHARED_FORMULA')
  }
  const drawingId = doc.getElementsByTagName('drawing')[0]?.getAttribute('r:id')
  if (!drawingId) return { formulas, image: undefined, notice: '原内部页没有产品图片，报客照片区留空' }
  const drawingTarget = relationship(path, drawingId)
  if (!drawingTarget) return { formulas, image: undefined, notice: '原内部页图片关系不完整，报客照片区留空' }
  const drawingPath = resolve(path, drawingTarget); const drawing = parse(xml(drawingPath))
  const blips = Array.from(drawing.getElementsByTagNameNS('*', 'blip'))
  if (blips.length !== 1) return { formulas, image: undefined, notice: `原内部页有${blips.length}个图片对象，无法唯一确定产品图，报客照片区留空` }
  const imageTarget = relationship(drawingPath, blips[0]!.getAttribute('r:embed') ?? '')
  const imagePath = imageTarget ? resolve(drawingPath, imageTarget) : ''
  const bytes = zip[imagePath]
  const extension = /\.png$/i.test(imagePath) ? 'png' : /\.jpe?g$/i.test(imagePath) ? 'jpeg' : undefined
  if (!bytes || !extension) return { formulas, image: undefined, notice: '产品图不是可支持的PNG/JPEG，报客照片区留空' }
  const extent = drawing.getElementsByTagNameNS('*', 'ext')[0]
  const dimensions = imagePixels(bytes, extension)
  const width = dimensions?.width ?? (Number(extent?.getAttribute('cx')) || 300)
  const height = dimensions?.height ?? (Number(extent?.getAttribute('cy')) || 200)
  return { formulas, image: { bytes, extension, width, height } as H360Image, notice: '' }
}
