import { HDD_CUSTOMER_TAB_COLORS } from '@/lib/huadeng.js'

export function HddTabColorLegend({ customers }: { customers: string[] }) {
  const selected = new Set(customers)
  const colors = Object.entries(HDD_CUSTOMER_TAB_COLORS).filter(([customer]) => selected.has(customer))
  if (!colors.length) return null
  return (
    <div aria-label="华登客户工作表标签颜色" style={{ margin: '12px 0', fontSize: 12, color: '#525252' }}>
      <p style={{ margin: '0 0 8px' }}>工作表标签颜色：同一客户的发票和续页使用同色，可在 Excel／WPS 底部标签查看。</p>
      <ul style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 18px', listStyle: 'none', margin: 0, padding: 0 }}>
        {colors.map(([customer, color]) => (
          <li key={customer} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span aria-hidden="true" style={{ width: 13, height: 13, borderRadius: 3, backgroundColor: `#${color}`, border: '1px solid #0002' }} />
            <span>{customer.trim()}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
