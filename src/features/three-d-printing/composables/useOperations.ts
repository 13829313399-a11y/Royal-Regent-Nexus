import { computed, onMounted, reactive, ref, watch } from "vue";
import { http, getApiErrorMessage } from "@/lib/http";
import { threeDPrintingApi } from "@/api/threeDPrinting";
import type {
  ThreeDProductionRecord,
  ThreeDInventoryMovement,
  ThreeDSchedule,
} from "@/types/threeDPrinting";
import { useWorkspaceContext } from "../context";
export function useOperations() {
  type Kind =
    | "spool"
    | "profile"
    | "request"
    | "file_alias"
    | "file"
    | "run_evidence";

  interface Item {
    id: string;
    kind: Kind;
    resource_key: string;
    revision: number;
    status: string;
    data: Record<string, unknown>;
  }

  interface Field {
    name: string;
    label: string;
    type?: string;
    default?: unknown;
    multiple?: boolean;
  }

  const base = "/three-d-printing/operations";

  const { canOperate, activeTab, editSchedule, authStore } =
    useWorkspaceContext();

  const kind = ref<Kind>("spool"),
    items = ref<Item[]>([]),
    page = ref(1),
    total = ref(0);

  const loading = ref(false),
    message = ref(""),
    reason = ref(""),
    resourceKey = ref(""),
    revision = ref(0),
    requestKey = ref(crypto.randomUUID());

  const form = reactive<Record<string, unknown>>({}),
    selectedFiles = ref<string[]>([]);
  const completionRuns = reactive<Record<string, string>>({});
  const completionFeedback = reactive<Record<string, string>>({});

  const labels: Record<Kind, string> = {
    spool: "卷材与 AMS",
    profile: "机台适配与保养",
    request: "内部需求",
    file_alias: "打印文件版本",
    file: "附件库",
    run_evidence: "质量与批次凭证",
  };

  const departmentNames: Record<string, string> = {
    "three-d-printing": "3D打印部",
    engineering: "工程部",
    production: "生产部",
    sales: "业务部",
    "pmc-warehouse": "PMC仓库",
  };
  const departments = computed(() =>
    Object.entries(departmentNames).filter(([key]) =>
      authStore?.grants?.some(
        (g) =>
          ["*", "huakang-a"].includes(g.factory_id) &&
          ["*", key].includes(g.department) &&
          (g.role_id === "admin" ||
            g.permissions.includes("three_d_printing:operate")),
      ),
    ),
  );
  const fields: Record<Kind, Field[]> = {
    spool: [
      { name: "material", label: "材料" },
      { name: "lot", label: "批次" },
      { name: "color", label: "颜色" },
      { name: "supplier", label: "供应商" },
      {
        name: "initial_g",
        label: "初始重量(g)",
        type: "number",
        default: 1000,
      },
      {
        name: "remaining_g",
        label: "实测余量(g)",
        type: "number",
        default: 1000,
      },
      { name: "low_g", label: "低余量阈值(g)", type: "number", default: 100 },
      {
        name: "machine_no",
        label: "机号（空白为未上机）",
        type: "number",
        default: null,
      },
      {
        name: "slot",
        label: "AMS 槽位（0–15）",
        type: "number",
        default: null,
      },
    ],
    profile: [
      { name: "machine_no", label: "机号（1–11）", type: "number", default: 1 },
      { name: "materials", label: "适用材料（逗号分隔）", type: "array" },
      {
        name: "product_ids",
        label: "适配产品（留空为不限）",
        type: "products",
        multiple: true,
        default: [],
      },
      {
        name: "service_interval_hours",
        label: "保养间隔(h)",
        type: "number",
        default: 250,
      },
      {
        name: "maintenance_blocked",
        label: "暂停参与排程",
        type: "checkbox",
        default: false,
      },
    ],
    request: [
      { name: "department", label: "申请部门" },
      { name: "cost_center", label: "成本中心" },
      { name: "product_id", label: "需求产品", type: "product" },
      { name: "quantity", label: "数量", type: "number", default: 1 },
      { name: "due_date", label: "交期", type: "date" },
      { name: "priority", label: "优先级", default: "normal" },
      { name: "note", label: "需求说明" },
    ],
    file_alias: [
      { name: "product_id", label: "对应产品", type: "product" },
      { name: "file_name", label: "打印机上报文件名" },
      { name: "version", label: "版本号" },
      { name: "file_id", label: "版本附件（可选）", type: "file" },
    ],
    file: [],
    run_evidence: [
      { name: "record_id", label: "生产记录", type: "records" },
      {
        name: "spool_ids",
        label: "使用卷材",
        type: "spool",
        multiple: true,
        default: [],
      },
      {
        name: "file_ids",
        label: "照片与附件",
        type: "file",
        multiple: true,
        default: [],
      },
      { name: "quality", label: "质量结论", default: "pending" },
      { name: "note", label: "核对说明" },
    ],
  };

  const states: Record<string, string> = {
    active: "有效",
    submitted: "待排产",
    approved: "已批准",
    rejected: "已驳回",
    scheduled: "已建计划",
    completed: "已完成",
    cancelled: "已取消",
  };

  const pending = ref<ThreeDProductionRecord[]>([]),
    pendingTotal = ref(0),
    pendingPage = ref(1),
    matchedProduct = ref(""),
    selectedRun = ref("");

  const thread = ref<{
    record: ThreeDProductionRecord;
    inventory_movements: ThreeDInventoryMovement[];
    file_versions: { version: string; file_name: string }[];
    requests: Item[];
    run_evidence: Item[];
    quality_flags: string[];
  }>();

  const advice = ref<
      {
        schedule_id: string;
        machine_no: number | null;
        reason: string;
        eta?: string;
        late?: boolean;
        product_name: string;
        quantity: number;
        due_date: string;
        schedule: ThreeDSchedule;
        warnings?: string[];
        assigned: boolean;
      }[]
    >([]),
    adviceMessage = ref("");

  const metrics = ref<
    {
      machine_no: number;
      availability: number | null;
      performance: number | null;
      quality: number | null;
      oee: number | null;
      hours_since_service_in_window: number;
      maintenance_due: boolean;
      lifetime_hours_since_service: number;
      pause_hours: number;
      waiting_hours: number;
      error_events: number;
      maintenance_reasons: string[];
    }[]
  >([]);

  const percent = (value: number | null) =>
    value === null ? "数据不足" : `${(value * 100).toFixed(1)}%`;

  const editing = computed(() => revision.value > 0);

  function reset() {
    Object.keys(form).forEach((k) => delete form[k]);
    fields[kind.value].forEach((f) => {
      form[f.name] = Array.isArray(f.default)
        ? [...f.default]
        : (f.default ?? "");
    });
    resourceKey.value = "";
    revision.value = 0;
    reason.value = "";
    selectedFiles.value = [];
    requestKey.value = crypto.randomUUID();
  }

  let listGeneration = 0;
  async function load(value = 1) {
    const generation = ++listGeneration;
    loading.value = true;
    try {
      const { data } = await http.get(`${base}/resources/${kind.value}`, {
        params: { page: value },
      });
      if (generation !== listGeneration) return;
      items.value = data.items;
      page.value = value;
      total.value = data.total;
    } catch (e) {
      if (generation === listGeneration) message.value = getApiErrorMessage(e);
    } finally {
      if (generation === listGeneration) loading.value = false;
    }
  }

  function edit(item: Item) {
    reset();
    Object.assign(form, item.data);
    fields[item.kind]
      .filter((f) => f.type === "array")
      .forEach((f) => {
        form[f.name] = (item.data[f.name] as string[]).join(", ");
      });
    selectedFiles.value = (item.data.file_ids as string[]) ?? [];
    resourceKey.value = item.resource_key;
    revision.value = item.revision;
  }

  async function save() {
    if (loading.value) return;
    loading.value = true;
    message.value = "";
    try {
      const data: Record<string, unknown> = {};
      for (const f of fields[kind.value]) {
        const v = form[f.name];
        data[f.name] =
          f.type === "array"
            ? String(v)
                .split(/[,，]/)
                .map((s) => s.trim())
                .filter(Boolean)
            : f.type === "number"
              ? v === "" || v === null
                ? null
                : Number(v)
              : v;
      }
      if (kind.value === "request") data.file_ids = selectedFiles.value;
      await http.post(`${base}/resources/${kind.value}`, {
        resource_key: resourceKey.value || requestKey.value,
        revision: revision.value,
        idempotency_key: requestKey.value,
        reason: reason.value.trim() || `保存${labels[kind.value]}`,
        data,
      });
      reset();
      await load();
      message.value = "已保存";
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
    }
  }

  async function act(item: Item, action: string) {
    if (loading.value) return;
    loading.value = true;
    try {
      await http.post(`${base}/resources/${item.id}/actions`, {
        revision: item.revision,
        idempotency_key: `${item.id}-${item.revision}-${action}`,
        reason:
          reason.value.trim() ||
          ({
            schedule: "需求直接排产",
            cancel: "取消需求",
            complete: "完成需求",
          }[action] ??
            action),
        action,
        target_id: action === "complete" ? (completionRuns[item.id] ?? "") : "",
        feedback: completionFeedback[item.id] ?? "",
      });
      await load(page.value);
      message.value = "操作完成";
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
    }
  }

  async function upload(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    loading.value = true;
    try {
      const body = new FormData();
      body.append("file", file);
      await http.post(`${base}/files`, body);
      await load();
      message.value = "附件已保存，可在需求、版本或质量凭证中按名称选择";
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
    }
  }

  async function download(item: Item) {
    try {
      const { data } = await http.get(`${base}/files/${item.id}`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = String(item.data.name);
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  }

  async function loadPending(value = 1) {
    try {
      const data = await threeDPrintingApi.collection<ThreeDProductionRecord>(
        "records",
        { quality: "pending", page: value },
      );
      pending.value = data.items;
      pendingTotal.value = data.total;
      pendingPage.value = value;
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  }

  async function match(run: ThreeDProductionRecord) {
    loading.value = true;
    try {
      await http.post(`${base}/runs/${run.id}/match`, {
        action: "match",
        target_id: matchedProduct.value,
        revision: run.revision,
        idempotency_key: `match-${run.id}-${run.revision}`,
        reason: reason.value.trim() || "人工匹配生产任务",
      });
      await loadPending(pendingPage.value);
      message.value = "匹配已保存，库存与成本结果请查看追溯";
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
    }
  }

  async function trace(id = selectedRun.value) {
    try {
      thread.value = (await http.get(`${base}/thread/${id}`)).data;
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  }

  async function analyze() {
    try {
      const [a, b] = await Promise.all([
        http.get(`${base}/recommendations`),
        http.get(`${base}/analytics`),
      ]);
      advice.value = a.data.items;
      adviceMessage.value = a.data.notice ?? a.data.blocked_reason ?? "";
      metrics.value = b.data.machines;
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  }

  async function prepare(item: (typeof advice.value)[number]) {
    editSchedule({ ...item.schedule, machine_no: item.machine_no ?? 0 });
    activeTab.value = "schedules";
  }

  async function applyAdvice(item: (typeof advice.value)[number]) {
    if (loading.value || !item.machine_no) return;
    loading.value = true;
    try {
      const s = item.schedule;
      await threeDPrintingApi.updateSchedule(s.id, {
        factory_id: "huakang-a",
        revision: s.revision,
        business_date: s.business_date,
        product_id: s.product_id,
        product_name: s.product_name,
        customer: s.customer,
        material_name: s.material_name,
        weight_g: s.weight_g,
        quantity: s.quantity,
        machine_no: item.machine_no,
        priority: s.priority,
        status: s.status,
        remark: s.remark,
      });
      await analyze();
      message.value = `${s.product_name}已分配至${item.machine_no}号机`;
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
    }
  }

  watch(kind, () => {
    reset();
    load();
  });

  onMounted(async () => {
    reset();
    await load();
    await loadPending();
    try {
      await analyze();
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  });
  return {
    departments,
    departmentNames,
    base,
    canOperate,
    activeTab,
    editSchedule,
    kind,
    items,
    page,
    total,
    loading,
    message,
    reason,
    resourceKey,
    revision,
    requestKey,
    form,
    selectedFiles,
    completionRuns,
    completionFeedback,
    labels,
    fields,
    states,
    pending,
    pendingTotal,
    pendingPage,
    matchedProduct,
    selectedRun,
    thread,
    advice,
    adviceMessage,
    metrics,
    percent,
    editing,
    reset,
    load,
    edit,
    save,
    act,
    upload,
    download,
    loadPending,
    match,
    trace,
    analyze,
    prepare,
    applyAdvice,
  };
}
