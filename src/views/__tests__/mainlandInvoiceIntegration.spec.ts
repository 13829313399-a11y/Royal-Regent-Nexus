import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { departmentModuleRegistry } from '@/data/enterpriseMock'

describe('mainland invoice integration boundaries', () => {
  it('adds one independent business card without moving existing cards', () => {
    const sales = departmentModuleRegistry['sales-business'].modules
    expect(sales.map(module => module.id)).toEqual([
      'internal-quote-desk', 'customer-price-conversion',
      'indonesia-material-shipment', 'po-schedule-intake', 'mainland-invoice',
    ])
    const invoice = sales.at(-1)!
    expect(invoice.route).toBe('/modules/sales-business/mainland-invoice')
    expect(invoice.factoryIds).toEqual(['huakang-a', 'huakang-b', 'huakang-d'])
    expect(invoice.permissions).toEqual(['mainland_invoice:generate'])
    expect(invoice.permissionDepartment).toBe('sales-business')
    expect(invoice.strictAccess).toBe(true)
    for (const [department, registry] of Object.entries(departmentModuleRegistry)) {
      if (department !== 'sales-business') {
        expect(registry.modules.some(module => module.id === 'mainland-invoice')).toBe(false)
      }
    }
  })

  it('preserves the global maintenance gate around the invoice code bundle', () => {
    const config = readFileSync('nginx.prod.conf', 'utf8')
    expect(config).toContain('if ($maintenance_gate = 1) { return 503; }')
    expect(config).toContain('location = /deployment-status.json')
    expect(config).toContain('location ^~ /mainland-invoice/')
    expect(config).not.toContain('alias /run/private-mainland-invoice')
  })

  it('keeps invoice activation opt-in without adding a database or exposing templates to Web', () => {
    const settings = readFileSync('backend/app/core/config.py', 'utf8')
    expect(settings).toContain('mainland_invoice_enabled: bool = False')
    const overlay = readFileSync('deploy/mainland-invoice.override.yml', 'utf8')
    expect(overlay).toContain('read_only: true')
    expect(overlay).not.toMatch(/^  (?:db|web):/m)
  })
})
