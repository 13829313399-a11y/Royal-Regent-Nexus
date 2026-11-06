/* eslint-disable */
// @ts-nocheck —— UI 胶水层；解析逻辑在 src/lib/factory.js
import { useRef, useState } from 'react'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { parseFactoryWorkbook } from '@/lib/factory.js'
import FactoryHka from '@/pages/FactoryHka.tsx'
import FactoryHkb from '@/pages/FactoryHkb.tsx'
import FactoryHkd from '@/pages/FactoryHkd.tsx'
import FactoryHxg from '@/pages/FactoryHxg.tsx'
import FactoryHdd from '@/pages/FactoryHdd.tsx'

const cardCls = 'rounded-xl border-neutral-200/90 shadow-[0_1px_2px_rgba(0,0,0,0.04)]'

/**
 * 厂区页（华康A/华康B/华兴/华登 共用）：规则与模板待对接，
 * 当前提供发票记录（出货明细表）上传预览：sheet 清单、数据行数、发票号识别数。
 */
export default function Factory({ site }) {
  if (site === '华康A') return <FactoryHka />
  if (site === '华康B') return <FactoryHkb />
  if (site === '华康D') return <FactoryHkd />
  if (site === '华兴') return <FactoryHxg />
  if (site === '华登') return <FactoryHdd />
  const [files, setFiles] = useState([]) // [{ name, status:'parsing'|'done'|'error', result, error }]
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  const onUpload = async (fileList) => {
    for (const file of Array.from(fileList || [])) {
      const buffer = await file.arrayBuffer()
      const magic = new Uint8Array(buffer.slice(0, 4))
      const isZip = magic[0] === 0x50 && magic[1] === 0x4b
      if (/\.xls$/i.test(file.name) || !isZip) {
        setFiles((prev) => [...prev.filter((x) => x.name !== file.name),
          { name: file.name, status: 'error', error: '老格式 .xls（或无效文件）：请先在 Excel/WPS 里「另存为 → .xlsx」再上传' }])
        continue
      }
      setFiles((prev) => [...prev.filter((x) => x.name !== file.name), { name: file.name, status: 'parsing' }])
      try {
        const result = parseFactoryWorkbook(buffer)
        setFiles((prev) => prev.map((x) => x.name === file.name ? { ...x, status: 'done', result } : x))
      } catch (e) {
        setFiles((prev) => prev.map((x) => x.name === file.name ? { ...x, status: 'error', error: String(e.message || e) } : x))
      }
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50 pb-28 text-neutral-900">
      <div className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <p className="text-xs font-medium tracking-[0.2em] text-teal-700">{site} · 大陆发票</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{site}厂区 · 发票记录</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-neutral-500">
            上传该厂区的发票记录（出货明细表 .xlsx），即可预览识别情况。
            发票生成规则与模板待对接后开放一键生成（需提供各客人的历史发票样张）。
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card className={cardCls}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">上传发票记录</CardTitle>
            <CardDescription>支持一次多选；上传后立即显示每个 sheet 的数据行数与识别到的发票数。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div
              className={`flex h-32 cursor-pointer items-center justify-center rounded-xl border border-dashed transition-colors ${dragOver ? 'border-teal-600 bg-teal-50/60' : 'border-neutral-300 bg-neutral-50/60 hover:border-teal-500/60 hover:bg-teal-50/40'}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); onUpload(e.dataTransfer.files) }}
            >
              <div className="text-center">
                <div className={`mx-auto flex h-10 w-10 items-center justify-center rounded-full border bg-white shadow-sm transition-colors ${dragOver ? 'border-teal-300 text-teal-700' : 'border-neutral-200 text-neutral-400'}`}>
                  <Upload className="h-4 w-4" />
                </div>
                <div className="mt-2.5 text-sm text-neutral-600">点击选择或拖拽发票记录到这里（可多选）</div>
                <div className="mt-1 text-xs text-neutral-400">仅支持 .xlsx</div>
              </div>
            </div>
            <input ref={fileRef} type="file" accept=".xlsx" multiple className="hidden" aria-label="发票记录上传"
              onChange={(e) => { onUpload(e.target.files); e.target.value = '' }} />
          </CardContent>
        </Card>

        {files.map((f) => (
          <Card key={f.name} className={cardCls}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <FileSpreadsheet className="h-4 w-4 text-teal-700" />
                <span className="font-mono text-sm">{f.name}</span>
                {f.status === 'done' && (
                  <Badge variant="outline" className="border-teal-200 bg-teal-50 font-normal text-teal-800">
                    {f.result.sheets.length} 个 sheet · 识别发票 {f.result.sheets.reduce((s, x) => s + (x.invoiceCount || 0), 0)} 张
                  </Badge>
                )}
                {f.status === 'parsing' && <span className="text-xs text-neutral-400">解析中…</span>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {f.status === 'error' && (
                <Alert variant="destructive" className="border-red-200 bg-red-50/60"><AlertDescription>{f.error}</AlertDescription></Alert>
              )}
              {f.status === 'done' && (
                <div className="max-h-96 overflow-auto rounded-lg border border-neutral-200 bg-white">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 z-10 border-b border-neutral-200 bg-neutral-50/95 text-xs text-neutral-500">
                      <tr>
                        <th className="px-3 py-2.5 text-left font-medium">sheet 名</th>
                        <th className="px-3 py-2.5 text-right font-medium">数据行</th>
                        <th className="px-3 py-2.5 text-left font-medium">发票号列</th>
                        <th className="px-3 py-2.5 text-right font-medium">识别发票数</th>
                        <th className="px-3 py-2.5 text-left font-medium">发票号样例</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.result.sheets.map((s) => (
                        <tr key={s.name} className="border-t border-neutral-100">
                          <td className="px-3 py-1.5 font-mono text-xs">{s.name}</td>
                          <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.dataRows}</td>
                          <td className="px-3 py-1.5 text-xs">{s.invCol || <span className="text-amber-600">未找到「发票号」表头</span>}</td>
                          <td className="px-3 py-1.5 text-right text-xs tabular-nums">{s.invoiceCount ?? '—'}</td>
                          <td className="px-3 py-1.5 font-mono text-xs text-neutral-500">{s.samples.join('、')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        ))}

        <p className="text-xs text-neutral-400">
          预览仅供核对识别情况；生成规则（模板、减价、票型分类等）按各厂区实际口径对接后开放。
        </p>
      </div>
    </div>
  )
}
