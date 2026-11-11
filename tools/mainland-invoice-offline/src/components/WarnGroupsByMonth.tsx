import { Alert, AlertDescription } from '@/components/ui/alert'

export interface WarnMonthItem {
  text: string
}

export interface WarnGroupsByMonthLabels {
  visible?: (n: number) => string
  unassigned?: (n: number) => string
  statics?: (n: number) => string
}

/**
 * 各厂区共用的「按月份提示问题」警告区（分组逻辑在 src/lib/warnMonth.js）：
 * 只列勾选月份的问题（切换月份即时更新）；「未注明月份」的问题和与月份无关的
 * 静态注意各自折叠成组，不混在按月列表里。全部为空且月份有勾选时不渲染。
 */
export function WarnGroupsByMonth({
  visible,
  unassigned = [],
  statics = [],
  monthSelEmpty = false,
  labels = {},
}: {
  visible: WarnMonthItem[]
  unassigned?: WarnMonthItem[]
  statics?: WarnMonthItem[]
  monthSelEmpty?: boolean
  labels?: WarnGroupsByMonthLabels
}) {
  if (!visible.length && !unassigned.length && !statics.length && !monthSelEmpty) return null
  const list = (items: WarnMonthItem[]) => (
    <div className="mt-1 max-h-48 overflow-auto pr-1">
      {items.map((w, i) => (
        <div key={i} className="mt-0.5 text-amber-700">{w.text}</div>
      ))}
    </div>
  )
  return (
    <Alert className="border-amber-200 bg-amber-50/60">
      <AlertDescription className="text-xs">
        {visible.length > 0 ? (
          <>
            <div className="font-medium text-amber-800">
              {labels.visible?.(visible.length) ?? `勾选月份的问题 ${visible.length} 条（照常生成，请人工核对）：`}
            </div>
            {list(visible)}
          </>
        ) : (
          <div className="font-medium text-amber-800">
            {monthSelEmpty
              ? '未勾选月份：问题提示已按月份隐藏，勾选月份后只看所选月份的问题。'
              : '当前勾选月份没有问题提示。'}
          </div>
        )}
        {unassigned.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer select-none font-medium text-amber-800">
              {labels.unassigned?.(unassigned.length) ?? `未注明月份的问题 ${unassigned.length} 条（点击展开）`}
            </summary>
            {list(unassigned)}
          </details>
        )}
        {statics.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer select-none font-medium text-amber-800">
              {labels.statics?.(statics.length) ?? `静态注意 ${statics.length} 条（与月份无关的内置提示，点击展开）`}
            </summary>
            {list(statics)}
          </details>
        )}
      </AlertDescription>
    </Alert>
  )
}
