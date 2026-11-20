import { http } from "@/lib/http";
import { createRandomUuid } from "@/lib/randomUuid";
import type {
  QuerySpec,
  QueryResult,
} from "@/features/injection-scheduling/types";

const root = "/injection-scheduling";
export const injectionApi = {
  async get<T = any>(path: string, params: object) {
    return (await http.get<T>(root + path, { params })).data;
  },
  async post<T = any>(path: string, data: object) {
    return (await http.post<T>(root + path, data, { timeout: 120000 })).data;
  },
  async patch<T = any>(path: string, data: object) {
    return (await http.patch<T>(root + path, data, { timeout: 120000 })).data;
  },
  query(payload: QuerySpec) {
    return this.post<QueryResult>("/demands/query", payload);
  },
  async upload(factory: string, file: File, revision: number) {
    const form = new FormData();
    form.append("factory_id", factory);
    form.append("file", file);
    form.append("base_revision", String(revision));
    form.append("client_operation_id", createRandomUuid());
    return (
      await http.post(root + "/imports", form, {
        timeout: 120000,
        headers: { "Content-Type": undefined },
      })
    ).data;
  },
  async export(payload: object) {
    const result = await http.post(root + "/exports/plan", payload, {
      responseType: "blob",
      timeout: 120000,
    });
    const url = URL.createObjectURL(result.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "注塑排产计划.xlsx";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  async downloadTemplate(factory: string, taskRows = 10) {
    const result = await http
      .get(root + "/templates/plan", {
        params: { factory_id: factory, task_rows: taskRows },
        responseType: "blob",
        timeout: 120000,
      })
      .catch(async (error) => {
        if (error.response?.data instanceof Blob) {
          const detail = JSON.parse(await error.response.data.text())?.detail;
          if (typeof detail === "string") throw new Error(detail);
        }
        throw error;
      });
    const url = URL.createObjectURL(result.data);
    const link = document.createElement("a");
    link.href = url;
    const names: Record<string, string> = {
      huaxing: "华兴",
      huadeng: "华登",
      "huakang-a": "华康A",
      "huakang-b": "华康B",
    };
    link.download = `${names[factory] || factory}_统一啤机计划表.xlsx`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
