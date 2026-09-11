import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { injectionApi as api } from '@/api/injectionScheduling'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import type {
  DataRow,
  FactoryId,
  FieldSpec,
  FilterNode,
  QuerySpec,
} from '@/features/injection-scheduling/types'

export const useInjectionStore = defineStore('injection-scheduling-v3', () => {
  const factory = ref<FactoryId | null>(null),
    revision = ref(0),
    sharedRevision = ref(0)
  const fields = ref<FieldSpec[]>([]),
    rows = ref<DataRow[]>([]),
    pending = ref<DataRow[]>([])
  const machines = ref<DataRow[]>([]),
    runs = ref<DataRow[]>([]),
    events = ref<DataRow[]>([])
  const summary = ref<Record<string, number>>({}),
    filteredSummary = ref<Record<string, number>>({})
  const filter = ref<FilterNode | null>(null),
    search = ref({ field: 'mold_code', mode: 'exact', text: '' })
  const sort = ref<{ field: string; direction: string }[]>([]),
    cursor = ref(0),
    nextCursor = ref<number | null>(null),
    total = ref(0)
  const selectedId = ref<string | null>(null),
    detail = ref<any>(null),
    drawer = ref(false)
  const busy = ref(false),
    loading = ref(false),
    dirty = ref(false),
    stale = ref(false),
    error = ref(''),
    notice = ref(''),
    syncedAt = ref('')
  const views = ref<DataRow[]>([]),
    settings = ref<Record<string, any>>({}),
    lastResult = ref<any>(null)
  let epoch = 0,
    loadSequence = 0,
    refreshSequence = 0
  let uncertainWrite: { key: string; payload: Record<string, unknown> } | null =
    null
  const fieldMap = computed(() =>
    Object.fromEntries(fields.value.map((f) => [f.key, f])),
  )
  const query = computed<QuerySpec>(() => ({
    factory_id: factory.value!,
    filter: filter.value,
    search: search.value,
    sort: sort.value,
    page_size: 100,
    cursor: cursor.value,
  }))
  function showError(e: unknown) {
    error.value =
      getApiErrorMessage(e) ||
      (e instanceof Error ? e.message : '请求失败，输入已保留')
  }
  async function select(id: string, open = false) {
    if (dirty.value) {
      error.value = '请先保存或取消当前输入，再切换需求'
      return
    }
    selectedId.value = id
    if (open) drawer.value = true
    const expected = epoch
    try {
      const result = await api.get('/demands/' + id, {
        factory_id: factory.value,
      })
      if (expected === epoch && selectedId.value === id && !dirty.value)
        detail.value = result
    } catch (e) {
      if (expected === epoch) showError(e)
    }
  }
  async function loadTable() {
    if (!factory.value) return
    if (dirty.value) {
      error.value = '请先保存或取消当前输入，再更改查询'
      return
    }
    const expected = epoch,
      seq = ++loadSequence
    try {
      const data = await api.query(query.value)
      if (expected !== epoch || seq !== loadSequence) return
      if (dirty.value) {
        stale.value = true
        return
      }
      rows.value = data.rows
      total.value = data.total_count
      nextCursor.value = data.next_cursor
      filteredSummary.value = data.filtered_summary
    } catch (e) {
      if (expected === epoch) showError(e)
    }
  }
  async function refresh() {
    if (!factory.value || busy.value) return
    if (dirty.value) {
      stale.value = true
      return
    }
    const expected = epoch,
      seq = ++refreshSequence
    loading.value = true
    try {
      const [totals, timeline, pool] = await Promise.all([
        api.get('/summary', { factory_id: factory.value }),
        api.get('/timeline', { factory_id: factory.value }),
        api.query({
          factory_id: factory.value,
          page_size: 500,
          filter: {
            op: 'and',
            children: [
              { field: 'planned_start_at', op: 'is_empty' },
              { field: 'remaining_shots', op: 'gt', value: 0 },
            ],
          },
        }),
      ])
      if (expected !== epoch || seq !== refreshSequence) return
      if (
        dirty.value ||
        totals.revision !== timeline.revision ||
        totals.revision !== pool.revision
      ) {
        stale.value = true
        return
      }
      summary.value = totals
      revision.value = Math.max(revision.value, totals.revision)
      sharedRevision.value = totals.shared_revision
      machines.value = timeline.machines
      runs.value = timeline.runs
      events.value = timeline.events
      pending.value = pool.rows
      await loadTable()
      if (selectedId.value) await select(selectedId.value)
      stale.value = false
      syncedAt.value = new Date().toLocaleTimeString('zh-CN', {
        hour12: false,
      })
    } catch (e) {
      if (expected === epoch) showError(e)
    } finally {
      if (expected === epoch && seq === refreshSequence) loading.value = false
    }
  }
  async function setFactory(id: FactoryId | null) {
    uncertainWrite = null
    ++epoch
    ++loadSequence
    ++refreshSequence
    busy.value = false
    loading.value = false
    revision.value = 0
    sharedRevision.value = 0
    lastResult.value = null
    factory.value = id
    selectedId.value = null
    detail.value = null
    drawer.value = false
    rows.value = []
    pending.value = []
    runs.value = []
    machines.value = []
    events.value = []
    fields.value = []
    summary.value = {}
    filteredSummary.value = {}
    views.value = []
    settings.value = {}
    cursor.value = 0
    total.value = 0
    filter.value = null
    search.value.text = ''
    error.value = ''
    notice.value = ''
    dirty.value = false
    stale.value = false
    if (!id) return
    const expected = epoch
    try {
      const [registry, prefs, saved] = await Promise.all([
        api.get('/field-registry', { factory_id: id }),
        api.get('/settings', { factory_id: id }),
        api.get('/views', { factory_id: id }),
      ])
      if (expected !== epoch) return
      fields.value = registry.fields
      settings.value = prefs.parameters
      views.value = saved
      await refresh()
    } catch (e) {
      if (expected === epoch) showError(e)
    }
  }
  async function mutate(
    path: string,
    data: object = {},
    method: 'post' | 'patch' = 'post',
  ) {
    if (busy.value || !factory.value) return null
    const expected = epoch
    busy.value = true
    if (path === '/plan-data/clear') {
      ++loadSequence
      ++refreshSequence
      loading.value = false
    }
    error.value = ''
    const key = JSON.stringify([factory.value, method, path, data])
    const payload =
      uncertainWrite?.key === key
        ? uncertainWrite.payload
        : {
            ...data,
            factory_id: factory.value,
            // Review dialogs freeze the board. Submit the version actually reviewed.
            base_revision:
              ['/plan-data/clear', '/execution/bulk-start'].includes(path) &&
              'expected_revision' in data
                ? data.expected_revision
                : revision.value,
            client_operation_id: createRandomUuid(),
          }
    uncertainWrite = { key, payload }
    try {
      const result = await api[method](path, payload)
      if (expected !== epoch) return null
      uncertainWrite = null
      lastResult.value = result
      revision.value = result.revision ?? revision.value
      if (result.cleared) {
        ++loadSequence
        ++refreshSequence
        selectedId.value = null
        detail.value = null
        drawer.value = false
        filter.value = null
        search.value.text = ''
        sort.value = []
        cursor.value = 0
        nextCursor.value = null
        rows.value = []
        pending.value = []
        runs.value = []
        summary.value = {}
        filteredSummary.value = {}
        total.value = 0
      }
      notice.value = result.cleared
        ? '本厂计划数据已清空；设备与模具资料已保留，可以重新导入 Excel'
        : result.bulk_start
          ? `已开工 ${result.started_count} 台；${result.failed_count} 台未开工`
          : 'save' in data && data.save === false
            ? `预览已完成，尚未保存；${result.unplaced?.length || 0} 条待处理`
            : result.unplaced?.length
              ? `已保存；${result.unplaced.length} 条需求待处理，请查看原因`
              : result.recalculate_required === false
                ? '导入完成，原计划未变更'
                : '已保存并重算'
      if (result.summary?.conflicts?.length)
        notice.value = `已处理无冲突内容；${result.summary.conflicts.length} 项冲突仍待处理`
      if (result.unified_import)
        notice.value = result.summary?.applied_count
          ? `导入完成；已按表记录 ${result.restored_assignment_count} 条机台安排，等待实际开工`
          : '导入完成，内容没有变化'
      dirty.value = false
      busy.value = false
      await refresh()
      return result
    } catch (e) {
      if (expected === epoch) {
        const status = (e as { response?: { status?: number } })?.response
          ?.status
        if (status && status >= 400 && status < 500) uncertainWrite = null
        showError(e)
        stale.value = true
      }
      return null
    } finally {
      if (expected === epoch) busy.value = false
    }
  }
  async function poll() {
    if (!factory.value || busy.value || loading.value || document.hidden) return
    const expected = epoch
    try {
      const response = await api.get('/changes', {
        factory_id: factory.value,
        since_revision: revision.value,
      })
      if (expected !== epoch) return
      if (
        response.changed ||
        response.shared_revision !== sharedRevision.value
      ) {
        if (dirty.value) stale.value = true
        else await refresh()
      } else
        syncedAt.value = new Date().toLocaleTimeString('zh-CN', {
          hour12: false,
        })
    } catch {
      if (expected === epoch) stale.value = true
    }
  }
  return {
    factory,
    revision,
    sharedRevision,
    fields,
    fieldMap,
    rows,
    pending,
    machines,
    runs,
    events,
    summary,
    filteredSummary,
    filter,
    search,
    sort,
    cursor,
    nextCursor,
    total,
    selectedId,
    detail,
    drawer,
    busy,
    loading,
    dirty,
    stale,
    error,
    notice,
    syncedAt,
    query,
    views,
    settings,
    lastResult,
    setFactory,
    refresh,
    loadTable,
    mutate,
    select,
    poll,
    showError,
  }
})
