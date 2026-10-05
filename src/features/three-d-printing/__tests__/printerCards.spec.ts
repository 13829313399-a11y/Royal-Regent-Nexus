import { nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { ThreeDPrinter } from '@/types/threeDPrinting'
import { workspaceKey } from '../context'
import { printerStateText } from '../printerPresentation'
import LegacyPrinterGrid from '../components/LegacyPrinterGrid.vue'

const printer = {
  id: 'machine-1', machine_no: 1, model: 'Bambu', connected: true,
  state: 'RUNNING', current_file: '真实文件.3mf', progress_percent: 42,
  remaining_minutes: 30, nozzle_temperature: 50, bed_temperature: 30,
} as ThreeDPrinter

describe('printer card display state', () => {
  it('shows progress only for a fresh running printer', async () => {
    const dashboard = ref({ printers: [{ ...printer }] })
    const selectedPrinter = ref('')
    const wrapper = mount(LegacyPrinterGrid, {
      global: { provide: { [workspaceKey as symbol]: { dashboard, selectedPrinter, stateLabel: printerStateText } } },
    })
    const card = () => wrapper.get('.legacy-machine')
    expect(card().get('[role="progressbar"]').attributes('aria-valuenow')).toBe('42')
    expect(card().text()).toContain('正在打印')

    for (const [state, label] of [
      ['PREPARE', '准备中'], ['PAUSE', '打印已暂停'], ['FINISH', '打印已完成'],
      ['ERROR', '设备异常'],
    ]) {
      dashboard.value = { printers: [{ ...printer, state }] }
      await nextTick()
      expect(card().text()).toContain(label)
      expect(card().find('[role="progressbar"]').exists()).toBe(false)
    }

    dashboard.value = { printers: [{ ...printer, connected: false, state: 'RUNNING' }] }
    await nextTick()
    expect(card().text()).toContain('离线')
    expect(card().text()).not.toContain('42%')
    expect(card().find('[role="progressbar"]').exists()).toBe(false)

    dashboard.value = { printers: [{ ...printer, status_stale: true, state: 'RUNNING' }] }
    await nextTick()
    expect(card().text()).toContain('等待状态更新')
    expect(card().text()).not.toContain('42%')
    expect(card().find('[role="progressbar"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
