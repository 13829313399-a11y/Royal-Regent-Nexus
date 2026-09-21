import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import PrinterDetail from "../components/PrinterDetail.vue";
import { printerStateText } from "../printerPresentation";
import type { ThreeDPrinter } from "@/types/threeDPrinting";

vi.mock("@/lib/http", () => ({
  http: { get: vi.fn(async () => ({ data: { events: [], commands: [] } })) },
  getApiErrorMessage: (e: Error) => e.message,
}));

const printer = {
  id: "preparing-printer", machine_no: 1, model: "Bambu", connected: true,
  state: "PREPARE", current_file: "测试产品.3mf", last_seen_at: "2026-09-21T06:00:00Z",
  progress_percent: 100, remaining_minutes: 0, nozzle_temperature: 50, bed_temperature: 30,
} as ThreeDPrinter;
let wrapper: ReturnType<typeof mount>;
afterEach(() => wrapper?.unmount());

describe("printer preparation", () => {
  it.each(["PREPARE", "PREPARING", "DOWNLOADING", "SLICING"])("shows %s as preparation without displaying old print progress", async (state) => {
    expect(printerStateText(state)).toBe("准备中");
    wrapper = mount(PrinterDetail, { props: { id: printer.id, printer: { ...printer, state } } });
    await flushPromises();
    expect(wrapper.get(".status-panel h3").text()).toBe("准备中");
    expect(wrapper.text()).toContain("正在下载文件或进行打印前准备");
    expect(wrapper.get(".task-panel h3").text()).toBe("当前打印任务");
    expect(wrapper.text()).toContain("测试产品.3mf");
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false);
    await wrapper.setProps({ printer: { ...printer, state: "RUNNING", progress_percent: 2 } });
    expect(wrapper.get(".status-panel h3").text()).toBe("正在打印");
    expect(wrapper.get('[role="progressbar"]').attributes("aria-valuenow")).toBe("2");
    expect(wrapper.text()).not.toContain("正在下载文件");
    await wrapper.setProps({ printer: { ...printer, connected: false, status_stale: true } });
    expect(wrapper.get(".status-panel h3").text()).toBe("设备离线");
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false);
  });
});
