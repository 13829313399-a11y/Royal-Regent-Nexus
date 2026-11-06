<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import BomVersionComparison from './BomVersionComparison.vue'
import BomApprovalCheck from './BomApprovalCheck.vue'
import MaterialBomUsage from './MaterialBomUsage.vue'
import BomMaterialMatching from './BomMaterialMatching.vue'
import { applyMaterialMatches, type MatchSelection } from './materialMatching'
import { engineeringApi as api, emptyBom, newNode, type Access, type Bom, type Material, type ImportPreview, type Node } from './api'

const auth = useAuthStore(), route = useRoute()
const tab = ref('boms'), access = ref<Access | null>(null), loading = ref(false), busy = ref(false)
const error = ref(''), notice = ref(''), materials = ref<Material[]>([]), boms = ref<Bom[]>([])
const q = ref(''), process = ref(''), group = ref(''), dirty = ref(false)
const selected = ref<Bom | null>(null), editing = ref(false), data = ref(emptyBom()), history = ref<Array<Bom | Material>>([])
const copyFrom = ref(''), copyVersion = ref<number | null>(null), reason = ref('工程资料维护')
const imported = ref<ImportPreview | null>(null), quantities = ref<Array<{ key: string; quantity: string; unit: string }>>([])
const materialForm = ref(blankMaterial()), editingMaterial = ref(false)
const pending = ref<{ path: string; body: unknown; kind: 'material' | 'bom' } | null>(null)
const editorEpoch = ref(0)
const usageMaterial = ref<Material | null>(null)
let generation = 0, historyGeneration = 0, previewGeneration = 0
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
function invalidateEditor() { usageMaterial.value = null; editorEpoch.value++; previewGeneration++; historyGeneration++; quantities.value = []; history.value = [] }
function statusLabel(value: string) { return ({ ACTIVE: "已审核", APPROVED: "已审核", DRAFT: "待审核", INACTIVE: "已停用" } as Record<string, string>)[value] || value }
function blankMaterial() { return { id: '', code: '', name: '', group: '01', unit: '', department: '', specification: '', color: '', old_code: '', attribute: '外购', warehouse_category: '', expected_version: 0 } }
const ready = computed(() => route.query.factory === 'huakang-c' && access.value?.enabled && access.value.schema_ready)
const locked = computed(() => busy.value || !!pending.value)
const can = (action: string) => ready.value && !!access.value?.permissions.includes(action)
const filteredMaterials = computed(() => materials.value.filter(m => (!group.value || m.data.engineering?.group.startsWith(group.value)) && (m.code + m.name).includes(q.value)))
const filteredBoms = computed(() => boms.value.filter(b => (b.data.item_no + b.data.name).includes(q.value)))
const activeMaterials = computed(() => materials.value.filter(m => m.status === 'ACTIVE' && m.data.engineering?.approval === 'APPROVED'))
const bomHistory = computed(() => history.value.filter((item): item is Bom => 'nodes' in item.data))
const processes = computed(() => [...new Set(data.value.nodes.map(n => n.process).filter(Boolean))])
function clear() { usageMaterial.value = null; access.value = null; materials.value = []; boms.value = []; selected.value = null; data.value = emptyBom(); history.value = []; imported.value = null; quantities.value = []; materialForm.value = blankMaterial(); editing.value = false; editingMaterial.value = false; pending.value = null; dirty.value = false; busy.value = false; error.value = ''; notice.value = ''; historyGeneration++; previewGeneration++ }
function message(e: unknown) { const x = e as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }; const detail = x.response?.data?.detail; return typeof detail === 'string' ? detail : detail ? '字段格式不完整，请核对必填项和用量。' : x.message || '操作失败，请重试。' }
function denied(e: unknown) { return [401, 403].includes((e as { response?: { status: number } }).response?.status || 0) }
function failure(e: unknown) { if (denied(e)) { generation++; clear() }; error.value = message(e) }
async function load() {
  invalidateEditor()
  const token = ++generation; loading.value = true; error.value = ''
  if (route.query.factory !== 'huakang-c') { clear(); loading.value = false; return }
  try { const a = await api.access(); if (token !== generation) return; access.value = a
    if (a.enabled && a.schema_ready) { const w = await api.workspace(); if (token !== generation) return; materials.value = w.materials; boms.value = w.boms
      if (selected.value && editing.value && !dirty.value && !pending.value) {
        const current = w.boms.find(b => b.id === selected.value?.id)
        selected.value = current || null; data.value = current ? clone(current.data) : emptyBom()
        if (!current) editing.value = false
      }
    }
  } catch (e) { if (token === generation) failure(e) } finally { if (token === generation) loading.value = false }
}
function discard() { return !locked.value && (!dirty.value || window.confirm('有未保存内容，是否放弃并继续？')) }
function switchTab(value: string) { if (!discard()) return; invalidateEditor(); tab.value = value; dirty.value = false; editing.value = false; editingMaterial.value = false; imported.value = null; history.value = []; q.value = '' }
function editBom(b?: Bom, copy = false) { if (!discard()) return; invalidateEditor(); selected.value = copy ? null : b || null; data.value = b ? clone(b.data) : emptyBom(); copyFrom.value = copy && b ? b.id : ''; copyVersion.value = copy && b ? b.version : null; if (copy) data.value.item_no = ''; editing.value = true; dirty.value = false; quantities.value = []; process.value = ''; history.value = []; reason.value = copy ? '复制新货号' : '工程资料维护' }
function editMaterial(m?: Material) { if (!discard()) return; invalidateEditor(); const f = blankMaterial(); materialForm.value = m ? { ...f, id: m.id, code: m.code, name: m.name, expected_version: m.version, unit: m.data.unit, group: m.data.engineering?.group || m.code.split('-').slice(0, -1).join('-'), department: m.data.engineering?.department || '', attribute: m.data.engineering?.attribute || '外购', specification: m.data.spec || '', color: m.data.color || '', old_code: m.data.old_code || '', warehouse_category: m.data.category || '' } : f; editingMaterial.value = true; dirty.value = false }
function choose(n: Node, event: Event) { const value = (event.target as HTMLSelectElement).value; const m = activeMaterials.value.find(m => `${m.id}:${m.version}` === value); if (m) { n.material_id = m.id; n.material_version = m.version; n.unit = m.data.unit; n.source_code = m.code; n.source_name = m.name } else if (!value) { n.material_id = ''; n.material_version = 0 }; dirty.value = true; quantities.value = [] }
function command(version: number) { return { factory_id: 'huakang-c', operation_id: crypto.randomUUID(), expected_version: version, reason: reason.value } }
function applyMatches(selections: MatchSelection[]) {
  if (!can('bom_write') || locked.value || loading.value || !editing.value || tab.value !== 'boms') return
  try {
    const nodes = applyMaterialMatches(data.value.nodes, materials.value, selections)
    invalidateEditor(); data.value.nodes = nodes; dirty.value = true
    notice.value = `已填入 ${selections.length} 条物料；请核对并保存 BOM 草稿，原有核对要求仍需处理。`
  } catch (e) { failure(e) }
}
function body() { return { ...command(selected.value?.version || 0), data: clone(data.value), copy_from: copyFrom.value, copy_version: copyVersion.value } }
async function send(path: string, payload: unknown, kind: 'material' | 'bom') { if (locked.value) return; invalidateEditor(); pending.value = { path, body: payload, kind }; await retry() }
async function retry() {
  const request = pending.value; if (!request || busy.value) return; const token = generation; busy.value = true; error.value = ''
  try { const result = await api.post(request.path, request.body); if (token !== generation) return
    pending.value = null; dirty.value = false; notice.value = '已保存，历史依据已保留。'
    if (request.kind === 'bom') { selected.value = result as Bom; data.value = clone((result as Bom).data); copyFrom.value = ''; copyVersion.value = null }
    else { editingMaterial.value = false; materialForm.value = blankMaterial() }
    await load()
  } catch (e) { if (token !== generation) return; const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500) pending.value = null
    failure(e)
  } finally { if (token === generation || !pending.value) busy.value = false }
}
async function showHistory(id: string) { if (!discard()) return; history.value = []; const token = generation, request = ++historyGeneration; try { const h = await api.history(id); if (token === generation && request === historyGeneration) history.value = h.items } catch (e) { if (token === generation && request === historyGeneration) failure(e) } }
async function previewUsage() { const token = generation, request = ++previewGeneration; try { const r = await api.preview(body()); if (token === generation && request === previewGeneration) quantities.value = r.items } catch (e) { if (token === generation && request === previewGeneration) failure(e) } }
async function fileChanged(event: Event) { const file = (event.target as HTMLInputElement).files?.[0]; if (!file || locked.value) return; const token = generation; busy.value = true; imported.value = null; error.value = ''; try { const r = await api.importPreview(file); if (token === generation) imported.value = r } catch (e) { if (token === generation) failure(e) } finally { if (token === generation) busy.value = false } }
function adoptImport() { if (!imported.value?.can_save || !discard()) return; invalidateEditor(); selected.value = null; data.value = clone(imported.value.data); copyFrom.value = ''; copyVersion.value = null; editing.value = true; dirty.value = true; tab.value = 'boms'; process.value = ''; quantities.value = []; reason.value = '历史 BOM 核对' }
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || pending.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(discard); onBeforeRouteUpdate(discard)
watch(data, () => { previewGeneration++; quantities.value = [] }, { deep: true, flush: 'sync' })
watch(() => [route.query.factory, auth.sessionVersion, auth.authorizationVersion], () => { generation++; clear(); void load() }, { immediate: true })
onBeforeUnmount(() => { generation++; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="engineering-space space-y-5">
    <PageHeader title="工程 BOM" eyebrow="华康 C · 工程部" description="维护物料、工程用量和工序依据，保存每次审核版本。">
      <template #actions><Button variant="outline" :disabled="loading || locked || dirty" @click="load">刷新资料</Button></template>
    </PageHeader>
    <p v-if="route.query.factory !== 'huakang-c'" role="status">请在华康 C 工程部打开本工作区。</p>
    <p v-if="loading" role="status">正在读取工程资料…</p>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-red-800">{{ error }}</p>
    <p v-if="notice" role="status" class="text-teal-800">{{ notice }}</p>
    <div v-if="pending && !busy" class="rounded-lg border p-3"><p>上次保存结果尚未确认，请使用原请求重试。</p><Button @click="retry">核对并重试原请求</Button></div>
    <SectionPanel v-if="access && !ready" title="工程基础尚未开放" subtitle="请管理员完成工程数据结构升级和启用设置；当前不会建立业务单据。" />
    <template v-if="ready">
      <nav class="flex flex-wrap gap-2" aria-label="工程工作区">
        <Button v-for="t in [{ id: 'boms', label: '工程 BOM' }, { id: 'materials', label: '物料档案' }, { id: 'import', label: '历史导入' }]" :key="t.id" :variant="tab === t.id ? 'default' : 'outline'" :aria-pressed="tab === t.id" :disabled="locked" @click="switchTab(t.id)">{{ t.label }}</Button>
      </nav>
      <SectionPanel v-if="tab === 'materials'" title="物料档案" subtitle="同一编码共用档案；负责部门变更保留原编码。">
        <div class="flex flex-wrap items-end gap-3"><label>查询<input v-model="q" placeholder="编码或名称" /></label><label>分类<select v-model="group"><option value="">全部</option><option v-for="g in ['01', '02', '03', '04']" :key="g">{{ g }}</option></select></label><Button :disabled="!can('material_write') || locked" @click="editMaterial()">新建物料</Button></div>
        <p v-if="!filteredMaterials.length" class="py-6 text-slate-500">暂无物料，可先建立并审核工程样本资料。</p>
        <div v-else class="overflow-x-auto"><table><thead><tr><th>编码／名称</th><th>单位／部门</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="m in filteredMaterials" :key="m.id"><td>{{ m.code }}<br>{{ m.name }}</td><td>{{ m.data.unit }} ／ {{ m.data.engineering?.department || '待补齐' }}</td><td>{{ statusLabel(m.status) }} · v{{ m.version }}</td><td class="space-x-2"><Button size="sm" variant="outline" :disabled="!can('material_write') || locked" @click="editMaterial(m)">维护</Button><Button size="sm" variant="outline" :disabled="!can('material_approve') || locked || dirty || m.status !== 'DRAFT'" @click="send(`/materials/${m.id}/approve`, command(m.version), 'material')">审核</Button><Button size="sm" variant="outline" :disabled="!can('material_write') || locked || dirty || m.status === 'INACTIVE'" @click="send(`/materials/${m.id}/deactivate`, command(m.version), 'material')">停用</Button><Button size="sm" variant="ghost" @click="showHistory(m.id)">历史</Button><Button size="sm" variant="outline" :disabled="dirty || locked || loading || !m.data.engineering" @click="usageMaterial = m">BOM 引用</Button></td></tr></tbody></table></div>
        <form v-if="editingMaterial" class="mt-5 rounded-xl border p-4" @submit.prevent="send('/materials', { ...materialForm, ...command(materialForm.expected_version) }, 'material')">
          <fieldset :disabled="locked || !can('material_write')" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" @input="dirty = true" @change="dirty = true">
            <label>编码（新建可留空续号）<input v-model="materialForm.code" :readonly="!!materialForm.id" /></label><label>分类前缀<input v-model="materialForm.group" required placeholder="例如 04-01" /></label><label>名称<input v-model="materialForm.name" required maxlength="255" /></label>
            <label>单位<input v-model="materialForm.unit" required /></label><label>负责部门<input v-model="materialForm.department" required /></label><label>规格<input v-model="materialForm.specification" /></label><label>颜色<input v-model="materialForm.color" /></label><label>旧编码<input v-model="materialForm.old_code" /></label>
            <label>物料属性<select v-model="materialForm.attribute"><option v-for="v in ['外购', '自制', '委外', '客供']" :key="v">{{ v }}</option></select></label><label>仓储分类<select v-model="materialForm.warehouse_category"><option value="">不适用／待核对</option><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option></select></label><label>修改说明<input v-model="reason" required /></label><Button type="submit">保存待审物料</Button>
          </fieldset>
        </form>
      </SectionPanel>
      <MaterialBomUsage v-if="tab === 'materials' && usageMaterial" :material="usageMaterial" :disabled="dirty || locked || loading" @denied="failure" />
      <SectionPanel v-if="tab === 'boms'" title="工程 BOM 列表" subtitle="草稿修订不会覆盖上一有效版本；不同货号请复制。">
        <div class="flex flex-wrap items-end gap-3"><label>查询<input v-model="q" placeholder="货号或名称" /></label><Button :disabled="!can('bom_write') || locked" @click="editBom()">新建 BOM</Button></div>
        <p v-if="!filteredBoms.length" class="py-6 text-slate-500">暂无工程 BOM。</p>
        <div v-else class="overflow-x-auto"><table><thead><tr><th>货号／名称</th><th>最新／有效版本</th><th>操作</th></tr></thead><tbody><tr v-for="b in filteredBoms" :key="b.id"><td>{{ b.data.item_no }}<br>{{ b.data.name }}</td><td>v{{ b.version }} {{ statusLabel(b.status) }} ／ {{ b.effective_version ? `v${b.effective_version}` : '未审核' }}</td><td class="space-x-2"><Button variant="outline" size="sm" :disabled="locked" @click="editBom(b)">查看／维护</Button><Button variant="outline" size="sm" :disabled="!can('bom_write') || locked" @click="editBom(b, true)">复制新货号</Button><Button variant="ghost" size="sm" @click="showHistory(b.id)">历史</Button></td></tr></tbody></table></div>
      </SectionPanel>
      <SectionPanel v-if="tab === 'boms' && editing" title="BOM 明细与工序清单">
        <label>按工序查看<select v-model="process"><option value="">全部工序</option><option v-for="p in processes" :key="p">{{ p }}</option></select></label>
        <form @submit.prevent="send(selected ? `/boms/${selected.id}` : '/boms', body(), 'bom')">
          <fieldset :disabled="locked || !can('bom_write')" @input="dirty = true; quantities = []" @change="dirty = true; quantities = []">
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label>货号<input v-model="data.item_no" required :readonly="!!selected" /></label><label>名称<input v-model="data.name" required /></label><label>规格<input v-model="data.specification" /></label><label>修改说明<input v-model="reason" required /></label><label>资料来源<input v-model="data.source_reference" /></label></div>
            <div class="my-4 flex flex-wrap items-end gap-3"><Button type="button" variant="outline" @click="data.nodes.push({ ...newNode(), parent: data.nodes[0]?.key || '' }); dirty = true">新增用料行</Button></div>
            <div class="overflow-x-auto"><table class="bom-lines"><thead><tr><th>行／上级</th><th>物料／来源</th><th>分子／分母</th><th>单位／工序</th><th>免损／备注</th><th>核对</th><th>操作</th></tr></thead><tbody><tr v-for="(n, i) in data.nodes" v-show="!process || n.process === process" :key="n.key"><td>{{ i + 1 }}<select v-model="n.parent" :aria-label="`第${i + 1}行上级`"><option value="">成品根项</option><option v-for="(p, j) in data.nodes.filter(p => p.key !== n.key)" :key="p.key" :value="p.key">{{ p.source_name || p.source_code || p.key.slice(0, 8) }} {{ j + 1 }}</option></select></td><td><select :value="n.material_id ? `${n.material_id}:${n.material_version}` : ''" :aria-label="`第${i + 1}行物料`" @change="choose(n, $event)"><option value="">待匹配物料</option><option v-if="n.material_id && !activeMaterials.some(m => m.id === n.material_id && m.version === n.material_version)" :value="`${n.material_id}:${n.material_version}`">{{ n.source_code }} {{ n.source_name }}（历史 v{{ n.material_version }}）</option><option v-for="m in activeMaterials" :key="m.id" :value="`${m.id}:${m.version}`">{{ m.code }} {{ m.name }}（v{{ m.version }}）</option></select><p>{{ n.source_code }} {{ n.source_name }}<span v-if="n.material_id"> · 物料 v{{ n.material_version }}</span></p><small v-if="n.source.row">来源 {{ n.source.sheet }} 第 {{ n.source.row }} 行</small></td><td><input v-model="n.numerator" :aria-label="`第${i + 1}行分子`" required inputmode="decimal" /><input v-model="n.denominator" :aria-label="`第${i + 1}行分母`" required inputmode="decimal" /></td><td>{{ n.unit || '待选物料' }}<input v-model="n.process" :aria-label="`第${i + 1}行工序`" placeholder="裁床／车缝／手工…" /></td><td><label><input v-model="n.exempt_loss" type="checkbox" /> 不计损耗</label><input v-model="n.note" :aria-label="`第${i + 1}行备注`" /></td><td><p v-if="n.review_required">来源用量／物料待核对</p><input v-model="n.review_note" :aria-label="`第${i + 1}行核对说明`" placeholder="核对依据" /><details v-if="Object.keys(n.source).length"><summary>来源原文</summary><dl><template v-for="(v, k) in n.source" :key="k"><dt>{{ k }}</dt><dd>{{ v }}</dd></template></dl></details></td><td><Button type="button" variant="ghost" size="sm" @click="data.nodes.splice(i, 1); dirty = true">删除</Button></td></tr></tbody></table></div>
            <Button type="submit" class="mt-4">保存 BOM 草稿</Button>
          </fieldset>
        </form>
        <div class="mt-3 flex flex-wrap gap-2"><Button variant="outline" :disabled="locked" @click="previewUsage">核对理论用量</Button><Button :disabled="!selected || selected.status !== 'DRAFT' || dirty || locked || !can('bom_approve')" @click="selected && send(`/boms/${selected.id}/approve`, command(selected.version), 'bom')">审核当前草稿</Button></div>
        <p class="mt-3 text-sm text-slate-500">此处为工程理论用量，不包含订单损耗、库存抵扣或采购取整。</p>
        <ul v-if="quantities.length" class="mt-3"><li v-for="v in quantities" :key="v.key">{{ data.nodes.find(n => n.key === v.key)?.source_name || v.key }}：{{ v.quantity }} {{ v.unit }}</li></ul>
      </SectionPanel>
      <BomMaterialMatching v-if="tab === 'boms' && editing" :key="editorEpoch" :nodes="data.nodes" :materials="materials" :disabled="!can('bom_write') || locked || loading" @apply="applyMatches" />
      <BomApprovalCheck v-if="tab === 'boms' && editing && selected" :key="editorEpoch" :bom="selected" :disabled="dirty || locked || loading" @denied="failure" />
      <SectionPanel v-if="tab === 'import'" title="历史 BOM 导入预览" subtitle="支持标准表头与已核对的旧版格式；只读解析，核对后保存为草稿。">
        <input type="file" accept=".xls,.xlsx" aria-label="选择历史 BOM 文件" :disabled="!can('import') || locked" @change="fileChanged" />
        <template v-if="imported"><p class="my-3">{{ imported.filename }}：{{ imported.row_count }} 行，{{ imported.material_count }} 个物料编码。</p><ul class="max-h-80 overflow-y-auto"><li v-for="(issue, i) in imported.issues" :key="i">第 {{ issue.row }} 行：{{ issue.message }} {{ issue.blocking ? '（需修正源文件）' : '' }}</li></ul><Button class="mt-4" :disabled="!imported.can_save || !can('bom_write') || locked" @click="adoptImport">进入 BOM 草稿核对</Button></template>
      </SectionPanel>
      <BomVersionComparison v-if="bomHistory.length >= 2" :versions="bomHistory" :disabled="dirty || locked || loading" @denied="failure" />
      <SectionPanel v-if="history.length" title="历史依据"><details v-for="h in history" :key="h.version" class="border-b py-2"><summary>v{{ h.version }} · {{ statusLabel(h.status) }} · {{ h.occurred_at }} · {{ h.reason }}</summary><p class="mt-2">操作人：{{ h.actor_id }}</p>
        <template v-if="'nodes' in h.data"><p>{{ h.data.item_no }} · {{ h.data.name }} · {{ h.data.specification }}</p><p>来源：{{ h.data.source_reference || '手工建立' }}</p><div class="max-h-80 overflow-auto"><table><thead><tr><th>物料</th><th>工序</th><th>分子／分母</th><th>单位</th><th>备注</th></tr></thead><tbody><tr v-for="n in h.data.nodes" :key="n.key"><td>{{ n.source_code }} {{ n.source_name }}</td><td>{{ n.process }}</td><td>{{ n.numerator }} ／ {{ n.denominator }}</td><td>{{ n.unit }}</td><td>{{ n.note }} {{ n.review_note }}</td></tr></tbody></table></div></template>
        <template v-else><p v-if="'code' in h">{{ h.code }} · {{ h.name }}</p><p>单位：{{ h.data.unit }} · 规格：{{ h.data.spec }} · 颜色：{{ h.data.color }}</p><p>负责部门：{{ h.data.engineering?.department }} · 属性：{{ h.data.engineering?.attribute }}</p></template></details></SectionPanel>
    </template>
  </main>
</template>

<style scoped>
.engineering-space label { display: flex; flex-direction: column; gap: .35rem; font-size: .875rem; color: var(--color-slate-700); }
.engineering-space input:not([type=checkbox]), .engineering-space select { border: 1px solid var(--color-slate-300); border-radius: var(--radius-md); padding: .5rem .65rem; background: white; width: 100%; min-width: 0; }
.engineering-space table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: .875rem; text-align: left; }
.engineering-space th { font-weight: 600; background: var(--color-slate-50); }
.engineering-space th, .engineering-space td { padding: .65rem; border-bottom: 1px solid var(--color-slate-200); vertical-align: top; }
.bom-lines { min-width: 1100px; }
.bom-lines td:nth-child(2) { min-width: 240px; max-width: 300px; }
.bom-lines td:nth-child(3) { width: 130px; }
.bom-lines input + input { margin-top: .4rem; }
</style>
