<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Trash2, RefreshCw, TriangleAlert, X } from '@lucide/vue';
import { injectionApi as api } from '@/api/injectionScheduling';
import { getApiErrorMessage } from '@/lib/http';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { factories, numberText, type FactoryId } from './types';
import { vInjDialog } from './composables/injDialog';
import InjButton from './components/ui/InjButton.vue';

type ClearPreview = {
  factory_id: FactoryId;
  revision: number;
  preview_token: string;
  confirmation_text: string;
  can_clear: boolean;
  requires_execution_confirmation: boolean;
  counts: Record<string, number>;
  preserved: Record<string, number>;
  imports: {
    id: string;
    file_name: string;
    sheet_name: string;
    status: string;
  }[];
};
const props = defineProps<{ canReport: boolean; canPlan: boolean }>();
const emit = defineEmits<{ close: []; cleared: [] }>();
const store = useInjectionStore();
const targetFactory = store.factory!;
const preview = ref<ClearPreview | null>(null);
const loading = ref(false),
  error = ref('');
let generation = 0;
const canSubmit = computed(
  () =>
    props.canPlan &&
    !loading.value &&
    !error.value &&
    !store.busy &&
    preview.value?.can_clear &&
    (!preview.value.requires_execution_confirmation || props.canReport),
);
const items = [
  ['demands', '需求'],
  ['runs', '排产任务'],
  ['shift_reports', '班次报工'],
  ['historical_outputs', '导入历史产量'],
  ['import_batches', '导入批次'],
  ['machine_runtime_resets', '清理机台占用/工艺'],
] as const;
function close() {
  if (!store.busy) emit('close');
}
async function loadPreview() {
  const expected = ++generation;
  loading.value = true;
  error.value = '';
  preview.value = null;
  try {
    const result = await api.post<ClearPreview>('/plan-data/clear-preview', {
      factory_id: targetFactory,
    });
    if (expected !== generation || store.factory !== targetFactory) return;
    preview.value = result;
  } catch (e) {
    if (expected === generation)
      error.value = getApiErrorMessage(e) || '清空范围读取失败，请重试';
  } finally {
    if (expected === generation) loading.value = false;
  }
}
async function submit() {
  if (!canSubmit.value || !preview.value || store.factory !== targetFactory)
    return;
  error.value = '';
  const result = await store.mutate('/plan-data/clear', {
    expected_revision: preview.value.revision,
    preview_token: preview.value.preview_token,
    // The single confirmation button acknowledges the displayed preview while
    // preserving the existing API's factory, audit and execution contract.
    confirmation: preview.value.confirmation_text,
    reason: '用户确认清除本厂计划数据',
    include_execution: preview.value.requires_execution_confirmation,
  });
  if (store.factory !== targetFactory) return;
  if (result?.cleared) emit('cleared');
  else error.value = store.error || '清空未完成，请重试或重新预览';
}
watch(() => store.factory, close);
onMounted(() => {
  // Existing dirty/busy guards also protect navigation and background refresh
  // while the user reviews a fixed destructive scope.
  store.dirty = true;
  void loadPreview();
});
onBeforeUnmount(() => {
  generation++;
  if (store.factory === targetFactory) store.dirty = false;
});
</script>

<template>
  <div class="inj-modal-backdrop">
    <section
      class="inj-modal inj-clear-plan"
      role="dialog"
      aria-modal="true"
      aria-labelledby="inj-clear-plan-title"
      aria-describedby="inj-clear-plan-scope"
      v-inj-dialog="{ close, busy: store.busy }"
    >
      <header class="inj-clear-header">
        <h2 id="inj-clear-plan-title"><Trash2 />清空本厂计划数据</h2>
        <button aria-label="关闭清空窗口" :disabled="store.busy" @click="close">
          <X />
        </button>
      </header>
      <div class="inj-clear-body">
        <p id="inj-clear-plan-scope">
          范围：<strong>{{ factories[targetFactory] }}全部计划数据</strong
          >，包含导入及手工新增的需求，不受当前筛选或分页影响。其他厂区的数据保留。
        </p>
        <p v-if="loading" role="status">正在核对清空范围…</p>
        <template v-else-if="preview">
          <div class="inj-clear-counts" aria-label="将清空的数据">
            <div v-for="[key, label] in items" :key="key">
              <span>{{ label }}</span
              ><strong>{{ numberText(preview.counts[key]) }}</strong>
            </div>
          </div>
          <p v-if="preview.counts.manual_demands" class="inj-clear-warning">
            包含
            {{ numberText(preview.counts.manual_demands) }}
            条手工新增需求，也会一并清空。
          </p>
          <p class="inj-clear-preserved">
            保留 {{ numberText(preview.preserved.machines) }} 台设备、{{
              numberText(preview.preserved.mold_masters)
            }}
            条公共模具、{{ numberText(preview.preserved.mold_assets) }}
            套实物模具，以及班制日历、排产参数和保存的视图。设备故障、维修状态保持不变。
          </p>
          <details v-if="preview.imports.length" class="inj-clear-imports">
            <summary>
              查看将清空的 {{ preview.imports.length }} 个导入批次
            </summary>
            <ul>
              <li v-for="batch in preview.imports" :key="batch.id">
                {{ batch.file_name }} · {{ batch.sheet_name }}
              </li>
            </ul>
          </details>
          <template v-if="preview.can_clear">
            <div
              v-if="preview.requires_execution_confirmation"
              class="inj-clear-execution"
            >
              <p>
                <TriangleAlert />包含
                {{ numberText(preview.counts.executed_runs) }}
                条已开工任务（其中
                {{ numberText(preview.counts.active_runs) }} 条在产/暂停）及
                {{ numberText(preview.counts.shift_reports) }} 条报工。
              </p>
              <p>
                点击“确认清除”将一并删除这些生产记录，并解除相关机台占用。
              </p>
              <p v-if="!canReport">
                当前账号没有报工权限，无法清空包含生产记录的数据。
              </p>
            </div>
            <p class="inj-muted">
              确认后将清除以上数据，此操作不能通过“撤销排产”恢复。完成后可重新导入 Excel。
            </p>
          </template>
          <p v-else class="inj-clear-preserved" role="status">
            本厂暂无可清空的计划数据，可关闭窗口后导入 Excel。
          </p>
        </template>
        <p v-if="error" class="inj-clear-warning" role="alert">{{ error }}</p>
      </div>
      <footer class="inj-actions">
        <InjButton
          v-if="error"
          :disabled="store.busy"
          :pending="loading"
          @click="loadPreview"
          ><template #icon><RefreshCw /></template>重新预览</InjButton
        >
        <span class="inj-spacer" />
        <button :disabled="store.busy" @click="close">取消</button>
        <InjButton
          class="inj-clear-submit"
          :disabled="!canSubmit"
          :pending="store.busy"
          @click="submit"
          >确认清除</InjButton
        >
      </footer>
    </section>
  </div>
</template>

<style scoped>
.inj-clear-plan {
  width: 680px;
  padding: 0;
  gap: 0;
  overflow: hidden;
}
.inj-clear-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--inj-line);
  flex: none;
}
.inj-clear-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 18px;
}
.inj-clear-body {
  overflow-y: auto;
  padding: 18px 22px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.inj-clear-body p {
  margin: 0;
}
.inj-clear-counts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.inj-clear-counts > div {
  border: 1px solid var(--inj-line);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.inj-clear-counts span {
  color: var(--inj-muted);
  font-size: 12px;
}
.inj-clear-counts strong {
  font: 600 20px var(--inj-font-mono);
}
.inj-clear-preserved {
  padding: 10px 12px;
  background: #eef8f5;
  border: 1px solid #cce7df;
  border-radius: 8px;
}
.inj-clear-warning,
.inj-clear-execution {
  padding: 10px 12px;
  background: #fff5f1;
  color: #943a23;
  border: 1px solid #f0c8ba;
  border-radius: 8px;
}
.inj-clear-execution p {
  margin-bottom: 8px;
}
.inj-clear-execution svg {
  display: inline-block;
  vertical-align: text-bottom;
  margin-right: 4px;
}
.inj-clear-imports {
  overflow-wrap: anywhere;
}
.inj-clear-imports ul {
  max-height: 120px;
  overflow: auto;
  margin: 8px 0 0;
  padding-left: 22px;
}
.inj-clear-plan .inj-actions {
  padding: 14px 22px;
  margin: 0;
}
.inj-clear-plan .inj-clear-submit:not(:disabled) {
  background: #b43f2c;
  color: white;
  border-color: #b43f2c;
}
@media (max-width: 600px) {
  .inj-clear-header,
  .inj-clear-body {
    padding: 14px;
  }
  .inj-clear-plan .inj-actions {
    padding: 12px 14px;
    gap: 6px;
  }
  .inj-clear-counts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
