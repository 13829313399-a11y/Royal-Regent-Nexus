import { Button } from 'antd'
import { publicAsset } from '../deployment'

const templates = {
  engineering: ['产品转移工程表', '下载工程表模板'],
  tools: ['工具及非生产物料', '下载物料模板'],
  quotes: ['供应商报价', '下载报价模板'],
  shipments: ['走货明细', '下载走货模板'],
} as const

export function ImportTemplateDownload({ kind, size }: {
  kind: keyof typeof templates
  size?: 'small'
}) {
  const [name, label] = templates[kind]
  return <Button size={size} href={publicAsset(import.meta.env.BASE_URL, `import-templates/${kind}.xlsx`)}
    download={`${name}导入模板.xlsx`}>{label}</Button>
}
