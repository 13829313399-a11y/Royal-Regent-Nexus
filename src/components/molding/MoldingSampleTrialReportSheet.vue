<script setup lang="ts">
import { computed } from 'vue'
import type {
  MoldingSampleItem,
  MoldingSampleOrder,
  MoldingSampleTrialReportData,
} from '@/types/moldingSample'

const props = withDefaults(defineProps<{
  order: MoldingSampleOrder
  item: MoldingSampleItem
  data: MoldingSampleTrialReportData
  companyName: string
  editable?: boolean
}>(), {
  editable: false,
})

const emit = defineEmits<{
  'update:data': [value: MoldingSampleTrialReportData]
}>()

const moldIssueOptions = [
  '咀油啤', '粘啤咀', '顶针不回', '困气', '针位披锋',
  '粘前模', '滑块不顺', '顶针高感', '气纹', '变形',
  '粘后模', '有返水', '漏运水', '砂孔', '走料不齐',
  '断针', '无进水', '推板不动', '混色', '细丝',
  '无排气', '齿针披锋', '顶模不稳', '夹口披锋', '顶针不足',
]
const partIssueOptions = [
  '困气', '针位披锋', '顶白', '行位披锋', '缩水',
  '气纹', '变形', '夹水纹', '冷胶纹', '顶不出',
  '混色', '细丝', '走料不齐', '夹口披锋', '拖花',
  '气泡', '色差', '顶针披锋', '缺口错位', '合模不足',
]
const machineBrands = ['博创（高速机）', '震德', '亿知密', '丰铁（立式机）', '海天', '其他']
const moldingModes = ['半自动', '全自动', '手动']
const coolingWaterOptions = ['冻水', '热水', '冰水']

const materialName = computed(() => props.data.material_name || props.item.material)
const materialShots = computed(() => props.data.material_shots || (props.item.shoot_qty ? String(props.item.shoot_qty) : ''))
const materialColor = computed(() => props.data.color || props.item.color)
const colorCode = computed(() => props.data.color_code || props.item.pigment_no)
const moldCondition = computed(() => props.data.mold_condition || moldPresenceLabel(props.item.mold_presence_status))
const waterRatioParts = computed(() => {
  const [left = '', right = ''] = props.data.water_ratio.split(/[：:]/, 2)
  return { left: left.trim(), right: right.trim() }
})

function display(value: string | number | null | undefined) {
  return String(value ?? '').trim() || ' '
}

function moldPresenceLabel(value: MoldingSampleItem['mold_presence_status']) {
  if (value === 'in_factory') return '已在本厂'
  if (value === 'out_of_factory') return '不在本厂'
  return ''
}

function updateText(field: Exclude<keyof MoldingSampleTrialReportData, 'mold_issues' | 'part_issues'>, value: string) {
  emit('update:data', { ...props.data, [field]: value })
}

function toggleIssue(kind: 'mold_issues' | 'part_issues', issue: string) {
  const current = props.data[kind]
  emit('update:data', {
    ...props.data,
    [kind]: current.includes(issue) ? current.filter((entry) => entry !== issue) : [...current, issue],
  })
}

function toggleToken(field: 'machine_model' | 'front_mold_water' | 'rear_mold_water' | 'other_trial_requirement', value: string) {
  const tokens = props.data[field].split('、').filter(Boolean)
  updateText(field, tokens.includes(value) ? tokens.filter((entry) => entry !== value).join('、') : [...tokens, value].join('、'))
}

function isTokenSelected(field: 'machine_model' | 'front_mold_water' | 'rear_mold_water' | 'other_trial_requirement', value: string) {
  return props.data[field].split('、').includes(value)
}

function updateWaterRatio(side: 'left' | 'right', value: string) {
  const left = side === 'left' ? value : waterRatioParts.value.left
  const right = side === 'right' ? value : waterRatioParts.value.right
  updateText('water_ratio', left.trim() || right.trim() ? `${left.trim()} : ${right.trim()}` : '')
}
</script>

<template>
  <article class="molding-trial-report-sheet" :class="{ 'is-editable': editable }">
    <header class="molding-trial-report-sheet__header">
      <div class="molding-trial-report-sheet__company">{{ companyName }}</div>
      <div class="molding-trial-report-sheet__title">工模试模（交模）验收回执</div>
      <div class="molding-trial-report-sheet__revision">R-234<br>V-1.0</div>
    </header>

    <section class="molding-trial-report-sheet__intro">
      <div>致：啤机部</div>
      <div>下单人员：<span class="report-underline">{{ display(order.eng_name) }}</span></div>
      <div>试模要求：由工程部（工模）填写</div>
      <div>下单日期：<span class="report-underline">{{ display(order.date) }}</span></div>
    </section>

    <table class="molding-trial-report-sheet__table molding-trial-report-sheet__base-table">
      <tbody>
        <tr>
          <th>客户名称：</th><td>{{ display(order.client_name) }}</td>
          <th>产品编号：</th><td>{{ display(order.order_number) }}</td>
          <th>模具供应商：</th><td><input v-if="editable" class="report-field" :value="data.mold_supplier" @input="updateText('mold_supplier', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.mold_supplier) }}</span></td>
        </tr>
        <tr>
          <th>产品名称：</th><td>{{ display(order.product_name) }}</td>
          <th>工模编号：</th><td>{{ display(item.mold_id) }}</td>
          <th>工模名称：</th><td>{{ display(item.mold_name) }}</td>
        </tr>
      </tbody>
    </table>

    <table class="molding-trial-report-sheet__table molding-trial-report-sheet__material-table">
      <colgroup><col style="width: 10%"><col style="width: 13%"><col style="width: 7%"><col style="width: 7%"><col style="width: 9%"><col style="width: 9%"><col style="width: 9%"><col style="width: 8%"><col style="width: 8%"><col style="width: 10%"><col style="width: 10%"></colgroup>
      <tbody>
        <tr>
          <th rowspan="3" class="molding-trial-report-sheet__material-stub">材料<br>数量（啤数）<br>重量（KG）<br><span>样板类别：</span><input v-if="editable" class="report-inline-field report-inline-field--stub" :value="data.sample_category" @input="updateText('sample_category', ($event.target as HTMLInputElement).value)"><span v-else class="report-underline report-underline--stub">{{ display(data.sample_category) }}</span></th>
          <th colspan="5">全原料</th>
          <th colspan="2">全水口料</th>
          <th colspan="3"><span class="report-ratio-label">水口比例</span><span class="report-ratio-control">（<input v-if="editable" class="report-ratio-input" aria-label="水口比例左侧" :value="waterRatioParts.left" @input="updateWaterRatio('left', ($event.target as HTMLInputElement).value)"><span v-else class="report-ratio-output">{{ display(waterRatioParts.left) }}</span><span class="report-ratio-separator">：</span><input v-if="editable" class="report-ratio-input" aria-label="水口比例右侧" :value="waterRatioParts.right" @input="updateWaterRatio('right', ($event.target as HTMLInputElement).value)"><span v-else class="report-ratio-output">{{ display(waterRatioParts.right) }}</span>）</span></th>
        </tr>
        <tr>
          <th>胶料：</th><th>啤数</th><th>重量</th><th>颜色</th><th>色粉编号</th>
          <th>啤数</th><th>重量</th><th>啤数</th><th>原料重量</th><th>水口重量</th>
        </tr>
        <tr>
          <td>{{ display(materialName) }}</td><td>{{ display(materialShots) }}</td><td><input v-if="editable" class="report-field report-field--center" :value="data.material_weight" @input="updateText('material_weight', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.material_weight) }}</span></td><td>{{ display(materialColor) }}</td><td>{{ display(colorCode) }}</td>
          <td><input v-if="editable" class="report-field report-field--center" :value="data.runner_material_shots" @input="updateText('runner_material_shots', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.runner_material_shots) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.runner_material_weight" @input="updateText('runner_material_weight', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.runner_material_weight) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.water_shots" @input="updateText('water_shots', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.water_shots) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.water_material_weight" @input="updateText('water_material_weight', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.water_material_weight) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.water_weight" @input="updateText('water_weight', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.water_weight) }}</span></td>
        </tr>
      </tbody>
    </table>

    <section class="molding-trial-report-sheet__special">
      <strong>特别要求：</strong>
      <textarea v-if="editable" class="report-area" :value="data.special_requirements || order.reason" @input="updateText('special_requirements', ($event.target as HTMLTextAreaElement).value)" />
      <span v-else>{{ display(data.special_requirements || order.reason) }}</span>
    </section>

    <table class="molding-trial-report-sheet__table molding-trial-report-sheet__requirements-table">
      <tbody>
        <tr>
          <td class="molding-trial-report-sheet__requirements-left">
            <div>试模要求　1）前模　<template v-for="option in coolingWaterOptions" :key="`front-${option}`"><label v-if="editable" class="report-check-label"><input type="checkbox" :checked="isTokenSelected('front_mold_water', option)" @change="toggleToken('front_mold_water', option)">{{ option }}</label><span v-else class="report-check-display">□{{ isTokenSelected('front_mold_water', option) ? '✓' : '' }}{{ option }}</span>　</template></div>
            <div>　　　　　2）后模　<template v-for="option in coolingWaterOptions" :key="`rear-${option}`"><label v-if="editable" class="report-check-label"><input type="checkbox" :checked="isTokenSelected('rear_mold_water', option)" @change="toggleToken('rear_mold_water', option)">{{ option }}</label><span v-else class="report-check-display">□{{ isTokenSelected('rear_mold_water', option) ? '✓' : '' }}{{ option }}</span>　</template></div>
            <div>　　　　　3）其他　<label v-if="editable" class="report-check-label"><input type="checkbox" :checked="isTokenSelected('other_trial_requirement', '定形模')" @change="toggleToken('other_trial_requirement', '定形模')">定形模</label><span v-else class="report-check-display">□{{ isTokenSelected('other_trial_requirement', '定形模') ? '✓' : '' }}定形模</span>　其他说明：<input v-if="editable" class="report-inline-field report-inline-field--wide" :value="data.other_trial_requirement_note" @input="updateText('other_trial_requirement_note', ($event.target as HTMLInputElement).value)"><span v-else class="report-underline report-underline--wide">{{ display(data.other_trial_requirement_note) }}</span></div>
          </td>
          <td class="molding-trial-report-sheet__requirements-right">
            <div>烤料时间：<input v-if="editable" class="report-inline-field report-inline-field--short" :value="data.baking_time_hours" @input="updateText('baking_time_hours', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.baking_time_hours) }}</span> 小时，请于＿＿＿＿前烤好</div>
            <div>工模状况：<template v-if="editable"><label class="report-check-label"><input type="checkbox" :checked="data.mold_condition === '已在本厂'" @change="updateText('mold_condition', ($event.target as HTMLInputElement).checked ? '已在本厂' : '')">已在本厂</label></template><template v-else>□{{ moldCondition === '已在本厂' ? '✓' : '' }}已在本厂</template>　□预计返模时间 <input v-if="editable" class="report-inline-field report-inline-field--short" :value="data.expected_return_time" @input="updateText('expected_return_time', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.expected_return_time) }}</span></div>
            <div>啤件毛重：<input v-if="editable" class="report-inline-field report-inline-field--short" :value="data.gross_weight" @input="updateText('gross_weight', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.gross_weight) }}</span>　净重：<input v-if="editable" class="report-inline-field report-inline-field--short" :value="data.net_weight" @input="updateText('net_weight', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.net_weight) }}</span></div>
          </td>
        </tr>
      </tbody>
    </table>

    <section class="molding-trial-report-sheet__parameters">
      <div class="molding-trial-report-sheet__section-caption">试模参数：（由啤机部填写）</div>
      <div class="molding-trial-report-sheet__machine-line">
        <div>适配机型：<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.plastic_model" @input="updateText('plastic_model', ($event.target as HTMLInputElement).value)"><span v-else class="report-underline report-underline--medium">{{ display(data.plastic_model) }}</span> 安士（A）</div>
        <div class="molding-trial-report-sheet__brands">
          <template v-for="brand in machineBrands" :key="brand">
            <label v-if="editable" class="report-check-label"><input type="checkbox" :checked="isTokenSelected('machine_model', brand)" @change="toggleToken('machine_model', brand)">{{ brand }}</label>
            <span v-else class="report-check-display">□{{ isTokenSelected('machine_model', brand) ? '✓' : '' }}{{ brand }}</span>
          </template>
        </div>
        <div>注塑机号：<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.machine_no || item.production_machine" @input="updateText('machine_no', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.machine_no || item.production_machine) }}</span></div>
      </div>
      <table class="molding-trial-report-sheet__table molding-trial-report-sheet__parameter-table">
        <tbody>
          <tr><th colspan="4">时间</th><th colspan="5">射胶</th><th colspan="3">电热温度</th><th rowspan="2">啤塑状态</th></tr>
          <tr><th>射胶</th><th>冷却</th><th>保压</th><th>周期</th><th>速度</th><th>1段</th><th>2段</th><th>3段</th><th>4段</th><th>头段</th><th>中段</th><th>尾段</th></tr>
          <tr>
            <td><input v-if="editable" class="report-field report-field--center" :value="data.injection_speed" @input="updateText('injection_speed', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.injection_speed) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.cooling_time" @input="updateText('cooling_time', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.cooling_time) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.holding_time" @input="updateText('holding_time', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.holding_time) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.cycle_time" @input="updateText('cycle_time', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.cycle_time) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.injection_speed" @input="updateText('injection_speed', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.injection_speed) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.pressure_stage_1" @input="updateText('pressure_stage_1', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.pressure_stage_1) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.pressure_stage_2" @input="updateText('pressure_stage_2', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.pressure_stage_2) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.pressure_stage_3" @input="updateText('pressure_stage_3', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.pressure_stage_3) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.pressure_stage_4" @input="updateText('pressure_stage_4', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.pressure_stage_4) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.barrel_temperature_head" @input="updateText('barrel_temperature_head', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.barrel_temperature_head) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.barrel_temperature_middle" @input="updateText('barrel_temperature_middle', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.barrel_temperature_middle) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.barrel_temperature_end" @input="updateText('barrel_temperature_end', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.barrel_temperature_end) }}</span></td>
            <td class="molding-trial-report-sheet__mode-cell"><template v-for="mode in moldingModes" :key="mode"><label v-if="editable" class="report-check-label"><input type="radio" name="molding-mode" :checked="data.molding_mode === mode" @change="updateText('molding_mode', mode)">{{ mode }}</label><span v-else>□{{ data.molding_mode === mode ? '✓' : '' }}{{ mode }}　</span></template></td>
          </tr>
          <tr class="molding-trial-report-sheet__parameter-extra-row"><th>顶针次数</th><th>枕压</th><th>锁模压力</th><th colspan="2">高压</th><th colspan="2">底压</th><th colspan="2">尾段</th><th colspan="3">手动</th><td rowspan="2"></td></tr>
          <tr class="molding-trial-report-sheet__parameter-extra-row"><td><input v-if="editable" class="report-field report-field--center" :value="data.ejector_count" @input="updateText('ejector_count', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.ejector_count) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.cushion_pressure" @input="updateText('cushion_pressure', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.cushion_pressure) }}</span></td><td><input v-if="editable" class="report-field report-field--center" :value="data.clamping_force" @input="updateText('clamping_force', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.clamping_force) }}</span></td><td colspan="2"><input v-if="editable" class="report-field report-field--center" :value="data.high_pressure" @input="updateText('high_pressure', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.high_pressure) }}</span></td><td colspan="2"><input v-if="editable" class="report-field report-field--center" :value="data.low_pressure" @input="updateText('low_pressure', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.low_pressure) }}</span></td><td colspan="2"><input v-if="editable" class="report-field report-field--center" :value="data.pressure_stage_4" @input="updateText('pressure_stage_4', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.pressure_stage_4) }}</span></td><td colspan="3"></td></tr>
        </tbody>
      </table>
    </section>

    <section class="molding-trial-report-sheet__section-caption molding-trial-report-sheet__issue-caption">模具问题记录事项</section>
    <section class="molding-trial-report-sheet__issues">
      <div class="molding-trial-report-sheet__issue-panel">
        <div class="molding-trial-report-sheet__issues-title">模具问题</div>
        <div class="molding-trial-report-sheet__issue-grid">
          <label v-for="issue in moldIssueOptions" :key="issue" class="molding-trial-report-sheet__issue-cell"><input v-if="editable" type="checkbox" :checked="data.mold_issues.includes(issue)" @change="toggleIssue('mold_issues', issue)"><span v-else class="report-check-display">□{{ data.mold_issues.includes(issue) ? '✓' : '' }}</span>{{ issue }}</label>
        </div>
      </div>
      <div class="molding-trial-report-sheet__issue-panel">
        <div class="molding-trial-report-sheet__issues-title">胶件问题</div>
        <div class="molding-trial-report-sheet__issue-grid">
          <label v-for="issue in partIssueOptions" :key="issue" class="molding-trial-report-sheet__issue-cell"><input v-if="editable" type="checkbox" :checked="data.part_issues.includes(issue)" @change="toggleIssue('part_issues', issue)"><span v-else class="report-check-display">□{{ data.part_issues.includes(issue) ? '✓' : '' }}</span>{{ issue }}</label>
        </div>
      </div>
    </section>

    <section class="molding-trial-report-sheet__notes"><strong>备注：</strong><textarea v-if="editable" class="report-area" :value="data.issue_notes" @input="updateText('issue_notes', ($event.target as HTMLTextAreaElement).value)" /><span v-else>{{ display(data.issue_notes) }}</span></section>
    <section class="molding-trial-report-sheet__summary"><strong>试模总结：</strong><textarea v-if="editable" class="report-area" :value="data.trial_summary" @input="updateText('trial_summary', ($event.target as HTMLTextAreaElement).value)" /><span v-else>{{ display(data.trial_summary) }}</span></section>

    <table class="molding-trial-report-sheet__table molding-trial-report-sheet__conclusion-table">
      <tbody>
        <tr><td colspan="3">第 <input v-if="editable" class="report-inline-field report-inline-field--short" :value="data.trial_round" @input="updateText('trial_round', ($event.target as HTMLInputElement).value)"><template v-else>{{ display(data.trial_round) }}</template> 次试模　　<label v-if="editable" class="report-check-label"><input type="radio" name="trial-verdict" :checked="data.verdict === '合格试模'" @change="updateText('verdict', '合格试模')">合格试模</label><span v-else>□{{ data.verdict === '合格试模' ? '✓' : '' }}合格试模</span>　　 <label v-if="editable" class="report-check-label"><input type="radio" name="trial-verdict" :checked="data.verdict === '不合格试模（退模厂改模）'" @change="updateText('verdict', '不合格试模（退模厂改模）')">不合格试模（退模厂改模）</label><span v-else>□{{ data.verdict === '不合格试模（退模厂改模）' ? '✓' : '' }}不合格试模（退模厂改模）</span></td></tr>
        <tr><td>试模员：<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.tester_name" @input="updateText('tester_name', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.tester_name) }}</span></td><td>啤机主管：<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.molding_supervisor_name" @input="updateText('molding_supervisor_name', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.molding_supervisor_name) }}</span></td><td>工程师（工模）：<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.engineer_name" @input="updateText('engineer_name', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.engineer_name) }}</span></td></tr>
        <tr><td>日期　<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.tester_date" @input="updateText('tester_date', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.tester_date) }}</span></td><td>日期　<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.molding_supervisor_date" @input="updateText('molding_supervisor_date', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.molding_supervisor_date) }}</span></td><td>日期　<input v-if="editable" class="report-inline-field report-inline-field--medium" :value="data.engineer_date" @input="updateText('engineer_date', ($event.target as HTMLInputElement).value)"><span v-else>{{ display(data.engineer_date) }}</span></td></tr>
      </tbody>
    </table>
    <footer class="molding-trial-report-sheet__footer">请啤机部填好本表交工程部存档，谢谢！</footer>
  </article>
</template>

<style>
.molding-trial-report-sheet { box-sizing: border-box; width: 210mm; height: 297mm; overflow: hidden; margin: 0 auto; padding: 5mm 5.5mm 3mm; background: #fff; color: #111; font-family: SimSun, "Microsoft YaHei", serif; font-size: 6.8px; line-height: 1.12; }
.molding-trial-report-sheet *, .molding-trial-report-sheet *::before, .molding-trial-report-sheet *::after { box-sizing: border-box; }
.molding-trial-report-sheet__header { position: relative; min-height: 15mm; padding: .8mm 15mm 1.4mm; text-align: center; }
.molding-trial-report-sheet__company { font-size: 17px; font-weight: 700; letter-spacing: .12em; }
.molding-trial-report-sheet__title { margin-top: 1.2mm; font-size: 9.5px; font-weight: 700; }
.molding-trial-report-sheet__revision { position: absolute; top: 4mm; right: 1mm; text-align: left; font-family: Arial, sans-serif; font-size: 7.2px; line-height: 1.08; }
.molding-trial-report-sheet__intro { display: grid; grid-template-columns: 1fr 1fr; gap: .8mm 13mm; margin: 0 0 1.2mm; font-size: 7.2px; }
.report-underline { display: inline-block; min-width: 33mm; border-bottom: 1px solid #111; }
.molding-trial-report-sheet__table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.molding-trial-report-sheet__table th, .molding-trial-report-sheet__table td { border: 1px solid #111; padding: .65mm .75mm; vertical-align: middle; overflow-wrap: anywhere; }
.molding-trial-report-sheet__table th { font-weight: 400; text-align: left; }
.molding-trial-report-sheet__base-table th { width: 10%; white-space: nowrap; }.molding-trial-report-sheet__base-table td { width: 23.33%; height: 5.3mm; font-size: 7.2px; }
.molding-trial-report-sheet__material-table { margin-top: 0; text-align: center; }.molding-trial-report-sheet__material-table th, .molding-trial-report-sheet__material-table td { height: 4.8mm; padding: .4mm; text-align: center; }.molding-trial-report-sheet__material-table th { font-size: 6.5px; }.molding-trial-report-sheet__material-stub { line-height: 1.23; }
.molding-trial-report-sheet__special { display: flex; min-height: 42mm; border: 1px solid #111; border-top: 0; padding: .9mm; }.molding-trial-report-sheet__special strong { white-space: nowrap; }.molding-trial-report-sheet__special > span { flex: 1; white-space: pre-wrap; }
.molding-trial-report-sheet__requirements-table td { height: 17mm; padding: .8mm; vertical-align: top; }.molding-trial-report-sheet__requirements-left { width: 48%; line-height: 1.62; }.molding-trial-report-sheet__requirements-right { line-height: 1.62; }
.molding-trial-report-sheet__parameters { border: 1px solid #111; border-top: 0; }.molding-trial-report-sheet__section-caption { height: 4.4mm; padding: .7mm; font-weight: 700; }.molding-trial-report-sheet__machine-line { display: grid; grid-template-columns: 25% 55% 20%; min-height: 8.2mm; border-top: 1px solid #111; }.molding-trial-report-sheet__machine-line > div { padding: .55mm .7mm; }.molding-trial-report-sheet__machine-line > div + div { border-left: 1px solid #111; }.molding-trial-report-sheet__brands { display: flex; flex-wrap: wrap; align-content: flex-start; gap: .55mm 1.7mm; }.report-check-label { display: inline-flex; align-items: center; gap: .4mm; white-space: nowrap; }.report-check-label input, .molding-trial-report-sheet__issue-cell input { width: 2.2mm; height: 2.2mm; margin: 0; accent-color: #111; }.report-check-display { white-space: nowrap; }.molding-trial-report-sheet__parameter-table { font-size: 6px; text-align: center; }.molding-trial-report-sheet__parameter-table th, .molding-trial-report-sheet__parameter-table td { height: 4.2mm; padding: .3mm; text-align: center; }.molding-trial-report-sheet__parameter-extra-row th, .molding-trial-report-sheet__parameter-extra-row td { height: 3.8mm; }.molding-trial-report-sheet__mode-cell { text-align: left !important; white-space: nowrap; }.molding-trial-report-sheet__mode-cell .report-check-label { display: block; margin-bottom: .3mm; }
.molding-trial-report-sheet__issue-caption { border: 1px solid #111; border-top: 0; }.molding-trial-report-sheet__issues { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid #111; border-top: 0; }.molding-trial-report-sheet__issue-panel + .molding-trial-report-sheet__issue-panel { border-left: 1px solid #111; }.molding-trial-report-sheet__issues-title { height: 4mm; padding: .65mm; border-bottom: 1px solid #111; text-align: center; font-weight: 700; }.molding-trial-report-sheet__issue-grid { display: grid; grid-template-columns: repeat(5, 1fr); }.molding-trial-report-sheet__issue-cell { display: flex; align-items: center; min-height: 3.9mm; padding: .5mm; border-right: 1px solid #111; border-bottom: 1px solid #111; font-size: 6.1px; white-space: nowrap; }.molding-trial-report-sheet__issue-cell:nth-child(5n) { border-right: 0; }.molding-trial-report-sheet__issue-cell:nth-last-child(-n + 5) { border-bottom: 0; }
.molding-trial-report-sheet__notes, .molding-trial-report-sheet__summary { display: flex; border: 1px solid #111; border-top: 0; padding: .85mm; white-space: pre-wrap; }.molding-trial-report-sheet__notes { min-height: 31mm; }.molding-trial-report-sheet__summary { min-height: 40mm; }.molding-trial-report-sheet__notes strong, .molding-trial-report-sheet__summary strong { white-space: nowrap; }
.molding-trial-report-sheet__conclusion-table td { height: 7.2mm; }.molding-trial-report-sheet__conclusion-table tr:first-child td { height: 6.2mm; text-align: center; }.molding-trial-report-sheet__footer { margin-top: .8mm; font-size: 6.5px; }
.report-field { width: 100%; height: 100%; min-height: 3.8mm; border: 0; outline: 0; background: transparent; padding: 0; font: inherit; color: inherit; }.report-field--center { text-align: center; }.report-inline-field { width: 16mm; border: 0; border-bottom: 1px solid #444; outline: 0; background: transparent; padding: 0 .35mm; font: inherit; color: inherit; }.report-inline-field--short { width: 11mm; }.report-inline-field--medium { width: 24mm; }.report-inline-field--wide { width: 43mm; }.report-inline-field--stub { width: 9mm; }.report-underline--medium { min-width: 24mm; }.report-underline--wide { min-width: 43mm; }.report-underline--stub { min-width: 9mm; }.report-ratio-label { white-space: nowrap; }.report-ratio-control { display: inline-flex; align-items: center; gap: .7mm; margin-left: 1mm; font-weight: 400; white-space: nowrap; }.report-ratio-input, .report-ratio-output { width: 10mm; min-width: 10mm; height: 3.4mm; border: 0; border-bottom: 1px solid #444; outline: 0; background: transparent; padding: 0; text-align: center; font: inherit; color: inherit; }.report-ratio-output { display: inline-flex; align-items: center; justify-content: center; }.report-ratio-separator { font-size: 8px; font-weight: 700; line-height: 1; }.report-area { flex: 1; min-height: inherit; resize: none; border: 0; outline: 0; background: transparent; padding: 0; font: inherit; color: inherit; line-height: 1.25; }.is-editable .report-field:focus, .is-editable .report-inline-field:focus, .is-editable .report-ratio-input:focus, .is-editable .report-area:focus { outline: 1px solid #0f766e; outline-offset: 1px; background: #f0fdfa; }.is-editable .molding-trial-report-sheet__issue-cell { cursor: pointer; }
.molding-sample-trial-report-print-root { display: none; }
@media print { @page { size: A4 portrait; margin: 0; } html, body { width: 210mm !important; height: 297mm !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; background: #fff !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; } body.molding-sample-trial-report-printing > * { display: none !important; } body.molding-sample-trial-report-printing .molding-sample-trial-report-print-root { display: block !important; position: absolute !important; inset: 0 !important; width: 210mm !important; height: 297mm !important; min-height: 297mm !important; max-height: 297mm !important; margin: 0 !important; overflow: hidden !important; break-after: avoid-page !important; page-break-after: avoid !important; break-inside: avoid-page !important; page-break-inside: avoid !important; } body.molding-sample-trial-report-printing .molding-trial-report-sheet { width: 210mm !important; height: 297mm !important; min-height: 297mm !important; max-height: 297mm !important; margin: 0 !important; overflow: hidden !important; break-after: avoid-page !important; page-break-after: avoid !important; break-inside: avoid-page !important; page-break-inside: avoid !important; } }
</style>
