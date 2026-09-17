import type { ThreeDPrinter } from "@/types/threeDPrinting";
export function freshestPrinter(live?: ThreeDPrinter, fetched?: ThreeDPrinter) {
  if (!live) return fetched;
  if (!fetched) return live;
  const left = Date.parse(live.last_seen_at) || 0,
    right = Date.parse(fetched.last_seen_at) || 0;
  if (left !== right) return left > right ? live : fetched;
  // Staleness can change without a new device timestamp.
  return live.status_stale || !live.connected ? live : fetched;
}
export interface PrinterEvent {
  id: string;
  state: string;
  observed_at: string;
  received_at?: string;
  progress?: number;
  current_file?: string;
  error_text?: string;
  connection_session_id?: string;
}
export const printerStateText = (state: string) =>
  ({
    RUNNING: "正在打印",
    PAUSE: "打印已暂停",
    IDLE: "空闲待机",
    FINISH: "打印已完成",
    FAILED: "打印失败",
    ERROR: "设备异常",
    OFFLINE: "设备离线",
    STALE: "等待状态更新",
    PREPARE: "准备打印",
    SLICING: "准备打印",
    UNKNOWN: "等待设备状态",
  })[state] || "待确认状态";
export function chinaTime(value: string) {
  if (!value) return "暂无上报";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "时间未记录";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(date);
}
export function groupPrinterEvents(events: PrinterEvent[]) {
  const groups: (PrinterEvent & { count: number; first_at: string })[] = [];
  for (const event of [...events].sort(
    (a, b) =>
      Date.parse(b.received_at || b.observed_at) -
      Date.parse(a.received_at || a.observed_at),
  )) {
    const last = groups.at(-1);
    const gap = last
      ? Date.parse(last.first_at) - Date.parse(event.observed_at)
      : Infinity;
    if (
      last &&
      gap >= 0 &&
      gap <= 90000 &&
      last.state === event.state &&
      last.current_file === event.current_file &&
      last.error_text === event.error_text &&
      last.connection_session_id === event.connection_session_id
    ) {
      last.count++;
      last.first_at = event.observed_at;
    } else groups.push({ ...event, count: 1, first_at: event.observed_at });
  }
  return groups;
}
