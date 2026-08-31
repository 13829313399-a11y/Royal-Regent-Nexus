import { computed, reactive, ref, watch, type Ref } from 'vue'
import { injectionSchedulingApi } from '@/api/injectionScheduling'
import { getApiErrorMessage } from '@/lib/http'
import type {
  InjectionScheduleBoard,
  InjectionScheduleBootstrap,
  InjectionScheduleMachine,
  InjectionScheduleMold,
  InjectionScheduleOrder,
} from '@/types/injectionScheduling'

export type InjectionScheduleViewMode = 'board' | 'table'

export function useInjectionScheduleWorkspace(factoryId: Ref<string>) {
  const bootstrap = ref<InjectionScheduleBootstrap | null>(null)
  const board = ref<InjectionScheduleBoard | null>(null)
  const orders = ref<InjectionScheduleOrder[]>([])
  const machines = ref<InjectionScheduleMachine[]>([])
  const molds = ref<InjectionScheduleMold[]>([])
  const loading = ref(false)
  const errorMessage = ref('')
  const viewMode = ref<InjectionScheduleViewMode>('table')
  const filters = reactive({
    search: '',
    status: '',
    priority: '',
    startDate: '',
    endDate: '',
  })
  let requestSequence = 0

  const visibleLines = computed(() => {
    const search = filters.search.trim().toLocaleLowerCase('zh-CN')
    return (board.value?.lines ?? []).filter((line) => {
      if (filters.status && line.status !== filters.status) return false
      if (filters.priority && line.priority !== filters.priority) return false
      if (!search) return true
      return [
        line.machine_code,
        line.mold_code,
        line.order_no,
        line.product_code,
        line.product_name,
      ].some((value) => value.toLocaleLowerCase('zh-CN').includes(search))
    })
  })
  const hasData = computed(() => Boolean(visibleLines.value.length || orders.value.length))

  async function refresh() {
    const sequence = ++requestSequence
    loading.value = true
    errorMessage.value = ''
    bootstrap.value = null
    board.value = null
    orders.value = []
    machines.value = []
    molds.value = []
    try {
      const [nextBootstrap, nextBoard, nextOrders, nextMachines, nextMolds] = await Promise.all([
        injectionSchedulingApi.bootstrap(factoryId.value),
        injectionSchedulingApi.board(factoryId.value, filters.startDate, filters.endDate),
        injectionSchedulingApi.orders(factoryId.value, filters),
        injectionSchedulingApi.machines(factoryId.value),
        injectionSchedulingApi.molds(factoryId.value),
      ])
      if (sequence !== requestSequence) return
      bootstrap.value = nextBootstrap
      board.value = nextBoard
      orders.value = nextOrders.items
      machines.value = nextMachines.items
      molds.value = nextMolds.items
      filters.startDate = nextBoard.start_date
      filters.endDate = nextBoard.end_date
    } catch (error) {
      if (sequence !== requestSequence) return
      errorMessage.value = getApiErrorMessage(error)
    } finally {
      if (sequence === requestSequence) loading.value = false
    }
  }

  function clearFilters() {
    filters.search = ''
    filters.status = ''
    filters.priority = ''
    filters.startDate = ''
    filters.endDate = ''
    void refresh()
  }

  watch(factoryId, () => {
    filters.search = ''
    filters.status = ''
    filters.priority = ''
    filters.startDate = ''
    filters.endDate = ''
    void refresh()
  }, { immediate: true })

  return {
    bootstrap,
    board,
    orders,
    machines,
    molds,
    loading,
    errorMessage,
    viewMode,
    filters,
    visibleLines,
    hasData,
    refresh,
    clearFilters,
  }
}
