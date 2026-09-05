import { computed, onMounted, reactive, ref, watch } from "vue";
import { http, getApiErrorMessage } from "@/lib/http";
import { threeDPrintingApi } from "@/api/threeDPrinting";
import type { ThreeDProductionRecord } from "@/types/threeDPrinting";
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
      { name: "product_ids", label: "适配产品ID（空白为不限）", type: "array" },
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
      { name: "file_id", label: "附件ID（可选）" },
    ],
    file: [],
    run_evidence: [
      { name: "record_id", label: "生产记录ID" },
      { name: "spool_ids", label: "使用卷材ID（逗号分隔）", type: "array" },
      { name: "file_ids", label: "照片/附件ID（逗号分隔）", type: "array" },
      { name: "quality", label: "质量结论", default: "pending" },
      { name: "note", label: "核对说明" },
    ],
  };

  const states: Record<string, string> = {
    active: "有效",
    submitted: "待审批",
    approved: "已批准",
    rejected: "已驳回",
    scheduled: "已建计划",
    completed: "已完成",
    cancelled: "已取消",
  };

  const fileItems = ref<Item[]>([]),
    filePage = ref(1),
    fileTotal = ref(0);

  const pending = ref<ThreeDProductionRecord[]>([]),
    pendingTotal = ref(0),
    pendingPage = ref(1),
    matchedProduct = ref(""),
    selectedRun = ref(""),
    feedback = ref("");

  const thread = ref<Record<string, unknown>>();

  const advice = ref<
      {
        schedule_id: string;
        machine_no: number | null;
        reason: string;
        eta?: string;
        late?: boolean;
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
      form[f.name] = f.default ?? "";
    });
    resourceKey.value = "";
    revision.value = 0;
    reason.value = "";
    selectedFiles.value = [];
    requestKey.value = crypto.randomUUID();
  }

  async function load(value = 1) {
    loading.value = true;
    try {
      const { data } = await http.get(`${base}/resources/${kind.value}`, {
        params: { page: value },
      });
      items.value = data.items;
      page.value = value;
      total.value = data.total;
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
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
        reason: reason.value,
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
    if (!reason.value.trim()) {
      message.value = "请先填写操作原因";
      return;
    }
    loading.value = true;
    try {
      await http.post(`${base}/resources/${item.id}/actions`, {
        revision: item.revision,
        idempotency_key: `${item.id}-${item.revision}-${action}`,
        reason: reason.value,
        action,
        target_id: selectedRun.value,
        feedback: feedback.value,
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
      await loadFiles();
      message.value = "附件已保存，可复制附件ID关联版本或选择关联需求";
    } catch (e) {
      message.value = getApiErrorMessage(e);
    } finally {
      loading.value = false;
    }
  }

  async function loadFiles(value = 1) {
    const { data } = await http.get(`${base}/resources/file`, {
      params: { page: value },
    });
    fileItems.value = data.items;
    fileTotal.value = data.total;
    filePage.value = value;
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
        reason: reason.value,
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
      adviceMessage.value = a.data.blocked_reason ?? "";
      metrics.value = b.data.machines;
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  }

  async function prepare(item: (typeof advice.value)[number]) {
    try {
      const result = await threeDPrintingApi.collection<
        import("@/types/threeDPrinting").ThreeDSchedule
      >("schedules", { q: item.schedule_id });
      const job = result.items.find((j) => j.id === item.schedule_id);
      if (!job) throw new Error("计划已变化，请刷新");
      editSchedule({ ...job, machine_no: item.machine_no ?? 0 });
      activeTab.value = "schedules";
    } catch (e) {
      message.value = getApiErrorMessage(e);
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
      await loadFiles();
      await analyze();
    } catch (e) {
      message.value = getApiErrorMessage(e);
    }
  });
  return {
    departments,
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
    labels,
    fields,
    states,
    fileItems,
    filePage,
    fileTotal,
    pending,
    pendingTotal,
    pendingPage,
    matchedProduct,
    selectedRun,
    feedback,
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
    loadFiles,
    download,
    loadPending,
    match,
    trace,
    analyze,
    prepare,
  };
}
