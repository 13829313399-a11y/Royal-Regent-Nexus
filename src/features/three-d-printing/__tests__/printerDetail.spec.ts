import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http } from "@/lib/http";
import type { ThreeDPrinter } from "@/types/threeDPrinting";
import PrinterDetail from "../components/PrinterDetail.vue";

vi.mock("@/lib/http", () => ({
  http: { get: vi.fn() },
  getApiErrorMessage: () => "未能确认操作结果；请先核对台账",
}));
const printer = {
  id: "p2", machine_no: 2, model: "Bambu", connected: true, state: "RUNNING",
  current_file: "实时打印任务", last_seen_at: "2026-10-12T02:30:00Z", progress_percent: 42,
  remaining_minutes: 60, nozzle_temperature: 254, bed_temperature: 70,
} as ThreeDPrinter;
const detail = { printer, events: [], commands: [] };
let wrapper: ReturnType<typeof mount> | undefined;
const panel = () => document.querySelector(".printer-overlay")!;

beforeEach(() => { vi.useFakeTimers(); vi.mocked(http.get).mockReset(); });
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers(); document.body.innerHTML = ""; });

describe("printer detail request recovery", () => {
  it.each([
    { isAxiosError: true, code: "ECONNABORTED" },
    { isAxiosError: true, response: { status: 504 } },
  ])("keeps live state on a read timeout and clears the error after refresh", async (error) => {
    vi.mocked(http.get).mockRejectedValueOnce(error).mockResolvedValue({ data: detail });
    wrapper = mount(PrinterDetail, { attachTo: document.body, props: { id: printer.id, printer, open: true } });
    await flushPromises();
    expect(panel().textContent).toContain("详情请求超时");
    expect(panel().textContent).not.toContain("操作结果");
    expect(panel().textContent).not.toContain("台账");
    expect(panel().querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow")).toBe("42");
    (panel().querySelector(".refresh-button") as HTMLButtonElement).click();
    await flushPromises();
    expect(http.get).toHaveBeenCalledTimes(2);
    expect(panel().querySelector('[role="alert"]')).toBeNull();
    expect(panel().textContent).toContain("实时打印任务");
  });

  it("cancels a closed drawer, stops polling and ignores its late response after reopening", async () => {
    let resolveOld!: (result: { data: typeof detail }) => void;
    vi.mocked(http.get).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
      .mockResolvedValue({ data: detail });
    wrapper = mount(PrinterDetail, { attachTo: document.body, props: { id: printer.id, printer, open: true } });
    const signal = vi.mocked(http.get).mock.calls[0]?.[1]?.signal as AbortSignal;
    await vi.advanceTimersByTimeAsync(30000);
    expect(http.get).toHaveBeenCalledTimes(1);
    await wrapper.setProps({ open: false });
    expect(signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(30000);
    expect(http.get).toHaveBeenCalledTimes(1);
    await wrapper.setProps({ open: true });
    await flushPromises();
    expect(http.get).toHaveBeenCalledTimes(2);
    resolveOld({ data: { ...detail, printer: { ...printer, last_seen_at: "2026-10-12T03:00:00Z", current_file: "已取消请求的错误结果" } } });
    await flushPromises();
    expect(panel().textContent).toContain("实时打印任务");
    expect(panel().textContent).not.toContain("已取消请求的错误结果");
    wrapper.unmount(); wrapper = undefined;
    await vi.advanceTimersByTimeAsync(30000);
    expect(http.get).toHaveBeenCalledTimes(2);
  });
});
