import type { ShippingScheduleTask } from '../../../../src/api/shippingTasks'

// The shared GitHub schedule page also offers the separate online shipping
// service. Standalone order packages have no such service or server credentials.
export async function listShippingTasks(
  _factoryId: string,
  _params: { q?: string; status?: string } = {},
): Promise<ShippingScheduleTask[]> {
  throw new Error('本机试用包未连接服务器船务排期；本地订单台账、发送和走货记录仍可正常使用。')
}
