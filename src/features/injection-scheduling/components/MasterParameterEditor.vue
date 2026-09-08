<script setup lang="ts">
import { computed, ref } from 'vue';
import { Plus, X } from '@lucide/vue';
import {
  numericEntry,
  objectFields,
  patchJsonPath,
  patchWorkingDay,
  type JsonValue,
} from '../parameterAdapter';
const props = defineProps<{
  modelValue: string;
  kind: string;
  label: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [string] }>();
const error = ref(''),
  addKey = ref('');
const parsed = computed<{ value: JsonValue; valid: boolean }>(() => {
  try {
    return { value: JSON.parse(props.modelValue || '{}'), valid: true };
  } catch {
    return { value: null, valid: false };
  }
});
const value = computed(() => parsed.value.value);
const object = computed<Record<string, JsonValue>>(() =>
  value.value && !Array.isArray(value.value) && typeof value.value === 'object'
    ? value.value
    : {},
);
const list = computed(() => (Array.isArray(value.value) ? value.value : []));
const known = computed(() => objectFields[props.kind] || []);
const matrix = computed(() =>
  [
    'allowed_upsize',
    'changeover_reference',
    'cleaning_matrix',
    'color_ranks',
  ].includes(props.kind),
);
const supported = computed(
  () =>
    matrix.value ||
    known.value.length ||
    ['working_days', 'daily_breaks'].includes(props.kind),
);
const unknown = computed(() =>
  known.value.length
    ? Object.keys(object.value).filter(
        (k) => !known.value.some((f) => f.key === k),
      )
    : [],
);
function commit(next: JsonValue) {
  if (props.disabled) return;
  emit('update:modelValue', JSON.stringify(next, null, 2));
  error.value = '';
}
function edit(path: (string | number)[], raw: string, type = 'text') {
  try {
    let original: any = value.value;
    for (const key of path) original = original?.[key];
    const replacement =
      type === 'number'
        ? numericEntry(raw, original)
        : type === 'boolean'
          ? raw === 'null'
            ? null
            : raw === 'true'
          : type === 'list'
            ? raw.split('\n').filter(Boolean)
            : type === 'numbers'
              ? raw
                  .split(/[,，\s]+/)
                  .filter(Boolean)
                  .map((x) => {
                    if (!Number.isFinite(Number(x)))
                      throw new Error('等级须为数字');
                    return Number(x);
                  })
              : raw === '' && original === null
                ? null
                : raw;
    commit(patchJsonPath(value.value, path, replacement));
  } catch (e) {
    error.value = String(e);
  }
}
function add() {
  const key = addKey.value.trim();
  if (!key) return;
  if (key in object.value) {
    error.value = '这个键已经存在';
    return;
  }
  if (
    ['allowed_upsize', 'changeover_reference'].includes(props.kind) &&
    !Number.isFinite(Number(key))
  ) {
    error.value = 'A 等级须为数字';
    return;
  }
  if (props.kind === 'cleaning_matrix' && !/^.*\|.*>.*\|.*$/.test(key)) {
    error.value = '请按 来源材料|色粉>目标材料|色粉 填写';
    return;
  }
  commit(
    patchJsonPath(
      value.value,
      [key],
      props.kind === 'allowed_upsize'
        ? []
        : props.kind === 'changeover_reference'
          ? [0, 0]
          : 0,
    ),
  );
  addKey.value = '';
}
const text = (v: JsonValue | undefined) => (v == null ? '' : String(v));
const lines = (v: JsonValue | undefined) =>
  Array.isArray(v) ? v.join('\n') : '';
</script>
<template>
  <section class="inj-parameter" :aria-label="label">
    <h3>{{ label }}</h3>
    <p v-if="kind === 'capabilities'" class="inj-muted">
      全自动状态不影响排期。夹具、吸盘等可人工装卸，记录供现场准备，不作为排产硬性条件。
    </p>
    <p v-else-if="kind === 'requirements'" class="inj-muted">
      夹具要求供现场装配准备，不限制排期。全自动状态也不参与排产限制。
    </p>
    <template v-if="parsed.valid && supported">
      <div v-if="kind === 'working_days'" class="inj-weekdays">
        <label
          v-for="(day, index) in [
            '周一',
            '周二',
            '周三',
            '周四',
            '周五',
            '周六',
            '周日',
          ]"
          :key="day"
          ><input
            type="checkbox"
            :disabled="disabled"
            :checked="list.includes(index)"
            @change="
              commit(
                patchWorkingDay(
                  value,
                  index,
                  ($event.target as HTMLInputElement).checked,
                ),
              )
            "
          />{{ day }}</label
        >
      </div>
      <template v-else-if="kind === 'daily_breaks'"
        ><div class="inj-json-rows">
          <div
            v-for="(period, index) in list"
            :key="index"
            class="inj-json-row"
          >
            <span>时段 {{ index + 1 }}</span
            ><input
              type="time"
              :disabled="disabled"
              :aria-label="'休息开始 ' + (index + 1)"
              :value="text((period as any)?.start)"
              @change="
                edit(
                  [index, 'start'],
                  ($event.target as HTMLInputElement).value,
                )
              "
            /><input
              type="time"
              :disabled="disabled"
              :aria-label="'休息结束 ' + (index + 1)"
              :value="text((period as any)?.end)"
              @change="
                edit([index, 'end'], ($event.target as HTMLInputElement).value)
              "
            /><button
              type="button"
              :disabled="disabled"
              :aria-label="'移除时段 ' + (index + 1)"
              @click="commit(list.filter((_, i) => i !== index))"
            >
              <X />
            </button>
          </div>
        </div>
        <button
          type="button"
          :disabled="disabled"
          @click="commit([...list, { start: '12:00', end: '13:00' }])"
        >
          <Plus />新增休息时段</button
        ><small>结束不晚于开始时，按跨午夜时段记录。</small></template
      >
      <template v-else-if="matrix"
        ><p v-if="kind === 'changeover_reference'" class="inj-muted">
          A 等级 / 换模分钟 / 换色分钟
        </p>
        <p v-if="kind === 'cleaning_matrix'" class="inj-muted">
          来源材料|色粉&gt;目标材料|色粉 → 清洗分钟
        </p>
        <p v-if="kind === 'color_ranks'" class="inj-muted">
          数字表示深浅顺序，保留业务原值。
        </p>
        <div class="inj-json-rows">
          <div v-for="(entry, key) in object" :key="key" class="inj-json-row">
            <span :title="String(key)"
              >{{ key
              }}{{
                ['allowed_upsize', 'changeover_reference'].includes(kind)
                  ? 'A'
                  : ''
              }}</span
            >
            <input
              v-if="kind === 'allowed_upsize' && Array.isArray(entry)"
              :disabled="disabled"
              :aria-label="label + ' ' + key"
              :value="entry.join(', ')"
              @change="
                edit(
                  [key],
                  ($event.target as HTMLInputElement).value,
                  'numbers',
                )
              "
            />
            <template
              v-else-if="
                kind === 'changeover_reference' &&
                Array.isArray(entry) &&
                entry.length >= 2
              "
              ><input
                v-for="i in [0, 1]"
                :key="i"
                :disabled="disabled"
                type="number"
                step="any"
                min="0"
                :aria-label="String(key) + 'A ' + (i ? '换色分钟' : '换模分钟')"
                :value="text(entry[i])"
                @change="
                  edit(
                    [key, i],
                    ($event.target as HTMLInputElement).value,
                    'number',
                  )
                "
            /></template>
            <input
              v-else-if="
                entry === null ||
                typeof entry === 'number' ||
                (typeof entry === 'string' && Number.isFinite(Number(entry)))
              "
              :disabled="disabled"
              type="number"
              step="any"
              :aria-label="label + ' ' + key"
              :value="text(entry)"
              @change="
                edit([key], ($event.target as HTMLInputElement).value, 'number')
              "
            />
            <small v-else>此项结构需在高级 JSON 中维护</small>
          </div>
        </div>
        <div class="inj-inline" v-if="!disabled">
          <input
            v-model="addKey"
            :aria-label="label + ' 新增键'"
            :placeholder="
              kind === 'cleaning_matrix'
                ? '来源材料|色粉>目标材料|色粉'
                : '新增等级或名称'
            "
          /><button type="button" @click="add"><Plus />新增</button>
        </div></template
      >
      <div v-else class="inj-form-grid">
        <label v-for="field in known" :key="field.key"
          ><span>{{ field.label }}</span>
          <select
            v-if="field.type === 'boolean'"
            :disabled="disabled"
            :value="
              object[field.key] == null ? 'null' : String(object[field.key])
            "
            @change="
              edit(
                [field.key],
                ($event.target as HTMLSelectElement).value,
                'boolean',
              )
            "
          >
            <option value="null">未填写</option>
            <option value="true">是</option>
            <option value="false">否</option>
          </select>
          <select
            v-else-if="field.type === 'select'"
            :disabled="disabled"
            :value="text(object[field.key])"
            @change="
              edit([field.key], ($event.target as HTMLSelectElement).value)
            "
          >
            <option value="">未填写</option>
            <option
              v-for="(name, key) in field.options"
              :key="key"
              :value="key"
            >
              {{ name }}
            </option>
            <option
              v-if="
                object[field.key] && !field.options?.[String(object[field.key])]
              "
              :value="text(object[field.key])"
            >
              {{ object[field.key] }}
            </option>
          </select>
          <textarea
            v-else-if="field.type === 'list'"
            :disabled="disabled"
            rows="3"
            :value="lines(object[field.key])"
            @change="
              edit(
                [field.key],
                ($event.target as HTMLTextAreaElement).value,
                'list',
              )
            "
          />
          <input
            v-else
            :disabled="disabled"
            :type="field.type === 'number' ? 'number' : 'text'"
            step="any"
            :value="text(object[field.key])"
            @change="
              edit(
                [field.key],
                ($event.target as HTMLInputElement).value,
                field.type,
              )
            "
          />
        </label>
      </div>
    </template>
    <p v-else class="inj-muted">
      此结构未提供专用表单，请使用原始 JSON；未编辑时保持原值。
    </p>
    <small v-if="unknown.length"
      >另有 {{ unknown.length }} 个字段保留于高级参数：{{
        unknown.join('、')
      }}</small
    >
    <details :open="!parsed.valid || !supported">
      <summary>高级 JSON</summary>
      <textarea
        :aria-label="label + ' 高级 JSON'"
        :disabled="disabled"
        :value="modelValue"
        rows="5"
        @input="
          emit(
            'update:modelValue',
            ($event.target as HTMLTextAreaElement).value,
          )
        "
      />
    </details>
    <p v-if="error" class="inj-error-text" role="alert">{{ error }}</p>
  </section>
</template>
