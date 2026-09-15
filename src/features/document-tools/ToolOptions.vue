<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import type { Capabilities, Operation, Source } from '@/api/documentTools'
import TranslationOptions from './TranslationOptions.vue'
import { mmToPt, normalizeCuts, parseGroups, ptToMm } from './coordinates'
const props = defineProps<{
  operation: Operation
  translationAvailability?: Capabilities['translation']
  source?: Source
  cuts: number[]
  axis: 'x' | 'y'
  extent: number
  suggestions: number[]
}>()
const options = defineModel<Record<string, unknown>>({ required: true })
const emit = defineEmits<{
  cuts: [values: number[]]
  axis: [value: 'x' | 'y']
  suggest: []
  undo: []
  redo: []
}>()
const units = ref('mm'),
  newCut = ref(100)
const sheets = computed(() => props.source?.manifest.sheets ?? [])
const groupPreview = computed(() => {
  try {
    return {
      groups: parseGroups(
        String(options.value.groups ?? ''),
        props.source?.manifest.pages?.length ?? 0,
      ),
      error: '',
    }
  } catch (error) {
    return {
      groups: [],
      error: error instanceof Error ? error.message : '分组无效',
    }
  }
})
const duplicates = computed(() => {
  const flat = groupPreview.value.groups.flat()
  return flat.length !== new Set(flat).size
})
const excelInput = computed(() => props.operation.startsWith('excel_'))
const translating = computed(() => props.operation.endsWith('_translate'))
function updateCut(index: number, raw: string) {
  const cuts = [...props.cuts]
  cuts[index] = units.value === 'mm' ? mmToPt(Number(raw)) : Number(raw)
  emit('cuts', normalizeCuts(cuts, props.extent))
}
function toggleSheet(name: string, checked: boolean) {
  const current = Array.isArray(options.value.sheets)
    ? (options.value.sheets as string[])
    : []
  options.value.sheets = checked
    ? [...current, name]
    : current.filter((value) => value !== name)
}
watch(
  () => props.axis,
  (value) => {
    options.value.axis = value
  },
)
</script>

<template>
  <div class="dt-options">
    <h3>输出设置</h3>
    <TranslationOptions v-if="translating" v-model="options" :availability="translationAvailability" />
    <p v-if="operation === 'word_translate'">翻译正文、表格及页眉页脚，输出 Word；图片内文字保留原样。</p>
    <p v-if="operation === 'excel_translate'">只翻译所选工作表的文字，保留公式、数字和格式；未选表示全部工作表（含隐藏表）。</p>
    <p v-if="operation === 'pdf_translate'">输出重新排版的译文 PDF 与 Word，扫描件需核对识别结果。</p>
    <label v-if="operation !== 'pdf_split' && (!translating || operation === 'pdf_translate')"
      >页面范围<input
        v-model="options.page_selection"
        placeholder="all 或 1-3,5"
      /><small>按文档页序号，从 1 开始；all 表示全部。</small></label
    >
    <label v-if="operation === 'pdf_to_word'"
      >输出目标<select v-model="options.layout_mode">
        <option value="editable">可编辑优先</option>
        <option value="layout">版式优先</option></select
      ><small>版式优先仍保留文字对象；复杂布局需核验。</small></label
    >
    <template v-if="operation === 'word_to_excel'">
      <label
        >提取内容<select v-model="options.word_mode">
          <option value="tables">原生表格</option>
          <option value="structure">全文结构</option>
        </select></label
      >
      <label class="dt-check"
        ><input
          v-model="options.include_notes_sheet"
          type="checkbox"
        />保留原文说明</label
      >
      <label class="dt-check"
        ><input
          v-model="options.include_headers_footers"
          type="checkbox"
        />包含页眉与页脚</label
      >
      <label class="dt-check"
        ><input
          v-model="options.merge_continuation_tables"
          type="checkbox"
        />合并连续表格</label
      >
    </template>
    <template v-if="operation === 'pdf_to_excel'">
      <label class="dt-check"
        ><input
          v-model="options.merge_continuation_tables"
          type="checkbox"
        />合并连续表格</label
      >
      <label class="dt-check"
        ><input
          v-model="options.preserve_merges"
          type="checkbox"
        />保留合并单元格</label
      >
      <label class="dt-check"
        ><input
          v-model="options.include_notes_sheet"
          type="checkbox"
        />保留说明与脚注</label
      >
      <label
        >数字格式<select v-model="options.numeric_locale">
          <option value="preserve_ambiguous">歧义数字保留原文</option>
          <option value="dot_decimal">点号为小数点</option>
          <option value="comma_decimal">逗号为小数点</option>
        </select></label
      >
    </template>
    <template v-if="excelInput">
      <fieldset>
        <legend>工作表</legend>
        <label
          v-for="sheet in sheets"
          :key="typeof sheet === 'string' ? sheet : sheet.name"
          class="dt-check"
          ><input
            type="checkbox"
            :checked="
              (options.sheets as string[] | undefined)?.includes(
                typeof sheet === 'string' ? sheet : sheet.name,
              )
            "
            @change="
              toggleSheet(
                typeof sheet === 'string' ? sheet : sheet.name,
                ($event.target as HTMLInputElement).checked,
              )
            "
          />{{ typeof sheet === 'string' ? sheet : sheet.name
          }}{{
            typeof sheet !== 'string' && sheet.hidden ? '（隐藏）' : ''
          }}</label
        ><small v-if="!sheets.length">读取文件后显示工作表。</small>
      </fieldset>
      <template v-if="!translating">
      <label
        >范围或命名区域<input
          v-model="options.range"
          placeholder="A1:H80；留空按原范围"
      /></label>
      <label class="dt-check"
        ><input v-model="options.include_hidden" type="checkbox" />包含隐藏行列
        / 工作表</label
      >
      <label
        >公式处理<select v-model="options.formula_mode">
          <option value="display">显示计算结果</option>
          <option value="formula">显示公式文本</option></select
        ><small>输出 Word / PDF 不再执行 Excel 公式。</small></label
      >
      <label v-if="operation === 'excel_to_pdf'"
        >分页策略<select v-model="options.print_mode">
          <option value="original">按原打印设置</option>
          <option value="fit_width">适合纸张宽度</option>
          <option value="selection">指定选区与纸张</option>
        </select></label
      >
      <div class="dt-two">
        <label
          >纸张<select v-model="options.paper">
            <option value="original">原设置</option>
            <option>A4</option>
            <option>A3</option>
          </select></label
        ><label
          >方向<select v-model="options.orientation">
            <option value="auto">自动</option>
            <option value="portrait">纵向</option>
            <option value="landscape">横向</option>
          </select></label
        >
      </div>
      </template>
    </template>
    <template v-if="operation === 'pdf_split'">
      <label
        >分页方式<select v-model="options.split_mode">
          <option value="groups">指定分组</option>
          <option value="each">每页一份</option>
          <option value="every_n">每 N 页一份</option>
          <option value="extract">提取并排序</option>
          <option value="double">左右双页拆分</option>
          <option value="crop">长页裁切分页</option>
        </select></label
      >
      <template
        v-if="['groups', 'extract'].includes(String(options.split_mode))"
        ><label
          >输出分组<textarea
            :value="String(options.groups ?? '')"
            rows="3"
            @input="
              options.groups = ($event.target as HTMLTextAreaElement).value
            "
            placeholder="1-3;4,6,5"
          /><small>分号分文件；逗号与区间按输入顺序输出。</small></label
        >
        <p v-if="groupPreview.error" role="alert">{{ groupPreview.error }}</p>
        <p
          v-for="(group, index) in groupPreview.groups"
          :key="index"
          class="dt-group"
        >
          文件 {{ index + 1 }}：{{ group.join('、') }}
        </p>
        <p v-if="duplicates" class="dt-warning">
          存在重复页，请选择保留或去重。
        </p>
        <label
          >重复页<select v-model="options.duplicate_policy">
            <option value="keep">保留输入顺序和重复页</option>
            <option value="deduplicate">去除重复页</option>
          </select></label
        ></template
      >
      <label v-if="options.split_mode === 'every_n'"
        >每份页数<input v-model.number="options.every_n" type="number" min="1"
      /></label>
      <template v-if="options.split_mode === 'crop'">
        <label
          >切线方向<select
            :value="axis"
            @change="
              emit(
                'axis',
                ($event.target as HTMLSelectElement).value as 'x' | 'y',
              )
            "
          >
            <option value="y">水平切线</option>
            <option value="x">垂直切线</option>
          </select></label
        >
        <div class="dt-two">
          <Button size="sm" variant="outline" @click="emit('undo')">撤销</Button
          ><Button size="sm" variant="outline" @click="emit('redo')"
            >重做</Button
          >
        </div>
        <label
          >位置单位<select v-model="units">
            <option value="mm">毫米 mm</option>
            <option value="pt">点 pt</option>
          </select></label
        >
        <div v-for="(cut, index) in cuts" :key="index" class="dt-cut-input">
          <label
            >切线 {{ index + 1
            }}<input
              type="number"
              step="0.1"
              :value="Number((units === 'mm' ? ptToMm(cut) : cut).toFixed(3))"
              @change="
                updateCut(index, ($event.target as HTMLInputElement).value)
              " /></label
          ><Button
            variant="ghost"
            size="sm"
            :aria-label="`删除切线 ${index + 1}`"
            @click="
              emit(
                'cuts',
                cuts.filter((_, i) => i !== index),
              )
            "
            >删除</Button
          >
        </div>
        <div class="dt-cut-input">
          <label
            >新增位置<input
              v-model.number="newCut"
              type="number"
              min="0"
              step="0.1" /></label
          ><Button
            variant="outline"
            size="sm"
            @click="
              emit(
                'cuts',
                normalizeCuts(
                  [...cuts, units === 'mm' ? mmToPt(newCut) : newCut],
                  extent,
                ),
              )
            "
            >添加</Button
          >
        </div>
        <Button variant="outline" size="sm" @click="emit('suggest')"
          >寻找空白 / 行边界</Button
        >
        <p v-if="suggestions.length">
          已找到 {{ suggestions.length }} 个候选切点。<Button
            variant="ghost"
            size="sm"
            @click="
              emit('cuts', normalizeCuts([...cuts, ...suggestions], extent))
            "
            >加入草稿</Button
          >
        </p>
        <div class="dt-group">
          <strong>切后预览 · {{ cuts.length + 1 }} 片</strong>
          <p v-for="(end, index) in [...cuts, extent]" :key="index">
            {{ index + 1 }}：{{
              ptToMm(index ? cuts[index - 1]! : 0).toFixed(1)
            }}–{{ ptToMm(end).toFixed(1) }} mm
          </p>
        </div>
        <small
          >拖动切线；方向键每次 0.5pt，Shift 每次
          10pt。裁切只改变可见范围，不删除底层隐藏内容。</small
        >
      </template>
    </template>
    <details>
      <summary>更多设置</summary>
      <label
        >输出文件名<input
          v-model="options.output_name"
          placeholder="留空使用原文件名" /></label
      ><label v-if="operation !== 'pdf_split' && !translating"
        >疑难区域 AI 增强<select v-model="options.ai_mode">
          <option value="auto">自动（仅不可靠区域）</option>
          <option value="off">关闭</option>
        </select></label
      >
    </details>
  </div>
</template>

<style scoped>
.dt-options {
  font-size: 13px;
  display: grid;
  gap: 14px;
}
.dt-options h3 {
  font-weight: 650;
}
.dt-options label {
  display: grid;
  gap: 6px;
  color: var(--foreground);
}
.dt-options input:not([type='checkbox']),
.dt-options select,
.dt-options textarea {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--input);
  border-radius: 8px;
  min-height: 36px;
  padding: 7px 9px;
  background: var(--card);
  font-size: 13px;
}
.dt-options .dt-check {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
}
.dt-options small {
  font-size: 12px;
  color: var(--muted-foreground);
  line-height: 1.65;
}
.dt-two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.dt-options fieldset {
  display: grid;
  gap: 4px;
}
.dt-options legend {
  margin-bottom: 6px;
}
.dt-options input[type='checkbox'] {
  accent-color: var(--primary);
}
.dt-cut-input {
  display: flex;
  align-items: end;
  gap: 6px;
}
.dt-cut-input label {
  flex: 1;
  min-width: 0;
}
.dt-group {
  background: var(--muted);
  padding: 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.7;
}
.dt-options details {
  border-top: 1px solid var(--border);
  padding-top: 12px;
}
.dt-options details label {
  margin-top: 12px;
}
.dt-options summary {
  cursor: pointer;
  font-weight: 600;
}
.dt-warning {
  color: #92400e;
}
.dt-options [role='alert'] {
  color: var(--destructive);
  font-size: 12px;
}
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 1px;
}
</style>
