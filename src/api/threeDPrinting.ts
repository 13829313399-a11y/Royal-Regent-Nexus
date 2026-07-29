import { http } from '@/lib/http'
import type {
  ThreeDAuditEvent,
  ThreeDDashboard,
  ThreeDInventory,
  ThreeDInventoryMovement,
  ThreeDMaintenance,
  ThreeDMaintenancePayload,
  ThreeDMaterial,
  ThreeDMaterialPayload,
  ThreeDPrinter,
  ThreeDProduct,
  ThreeDProductPayload,
  ThreeDProductionRecord,
  ThreeDRecordPayload,
  ThreeDSchedule,
  ThreeDSchedulePayload,
  ThreeDSettings,
} from '@/types/threeDPrinting'

const factoryId = 'huakang-b' as const
const base = '/three-d-printing'

export const threeDPrintingApi = {
  async dashboard(dateFrom = '', dateTo = '') {
    const response = await http.get<ThreeDDashboard>(`${base}/dashboard`, {
      params: {
        factory_id: factoryId,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      },
    })
    return response.data
  },
  async updateSettings(payload: Omit<ThreeDSettings, 'updated_at'>) {
    const response = await http.put<ThreeDSettings>(`${base}/settings`, payload)
    return response.data
  },
  async createMaterial(payload: ThreeDMaterialPayload) {
    const response = await http.post<ThreeDMaterial>(`${base}/materials`, payload)
    return response.data
  },
  async updateMaterial(id: string, payload: ThreeDMaterialPayload & { revision: number }) {
    const response = await http.put<ThreeDMaterial>(`${base}/materials/${id}`, payload)
    return response.data
  },
  async archiveMaterial(id: string) {
    await http.delete(`${base}/materials/${id}`, { params: { factory_id: factoryId } })
  },
  async createProduct(payload: ThreeDProductPayload) {
    const response = await http.post<ThreeDProduct>(`${base}/products`, payload)
    return response.data
  },
  async updateProduct(id: string, payload: ThreeDProductPayload & { revision: number }) {
    const response = await http.put<ThreeDProduct>(`${base}/products/${id}`, payload)
    return response.data
  },
  async archiveProduct(id: string) {
    await http.delete(`${base}/products/${id}`, { params: { factory_id: factoryId } })
  },
  async uploadProductImage(id: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<ThreeDProduct>(`${base}/products/${id}/image`, form, {
      params: { factory_id: factoryId },
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30_000,
    })
    return response.data
  },
  async removeProductImage(id: string) {
    await http.delete(`${base}/products/${id}/image`, {
      params: { factory_id: factoryId },
    })
  },
  async createRecord(payload: ThreeDRecordPayload) {
    const response = await http.post<ThreeDProductionRecord>(`${base}/records`, payload)
    return response.data
  },
  async updateRecord(id: string, payload: ThreeDRecordPayload & { revision: number }) {
    const response = await http.put<ThreeDProductionRecord>(`${base}/records/${id}`, payload)
    return response.data
  },
  async deleteRecord(id: string) {
    await http.delete(`${base}/records/${id}`, { params: { factory_id: factoryId } })
  },
  async setDayOff(businessDate: string, isDayOff: boolean, revision = 1) {
    await http.put(`${base}/day-status`, {
      factory_id: factoryId,
      business_date: businessDate,
      is_day_off: isDayOff,
      revision,
    })
  },
  async adjustInventory(materialName: string, targetStockG: number, minStockG: number, reason: string) {
    const response = await http.post<ThreeDInventory>(`${base}/inventory/adjust`, {
      factory_id: factoryId,
      material_name: materialName,
      target_stock_g: targetStockG,
      min_stock_g: minStockG,
      reason,
    })
    return response.data
  },
  async stockIn(payload: {
    business_date: string
    material_name: string
    amount_g: number
    vendor: string
    cost: number
    remark: string
  }) {
    const response = await http.post<ThreeDInventoryMovement>(`${base}/inventory/stock-in`, {
      factory_id: factoryId,
      ...payload,
    })
    return response.data
  },
  async createSchedule(payload: ThreeDSchedulePayload) {
    const response = await http.post<ThreeDSchedule>(`${base}/schedules`, payload)
    return response.data
  },
  async updateSchedule(id: string, payload: ThreeDSchedulePayload & { revision: number }) {
    const response = await http.put<ThreeDSchedule>(`${base}/schedules/${id}`, payload)
    return response.data
  },
  async updateScheduleStatus(id: string, status: ThreeDSchedule['status'], revision: number) {
    const response = await http.put<ThreeDSchedule>(`${base}/schedules/${id}/status`, {
      factory_id: factoryId,
      status,
      revision,
    })
    return response.data
  },
  async deleteSchedule(id: string) {
    await http.delete(`${base}/schedules/${id}`, { params: { factory_id: factoryId } })
  },
  async createMaintenance(payload: ThreeDMaintenancePayload) {
    const response = await http.post<ThreeDMaintenance>(`${base}/maintenance`, payload)
    return response.data
  },
  async updateMaintenance(id: string, payload: ThreeDMaintenancePayload & { revision: number }) {
    const response = await http.put<ThreeDMaintenance>(`${base}/maintenance/${id}`, payload)
    return response.data
  },
  async deleteMaintenance(id: string) {
    await http.delete(`${base}/maintenance/${id}`, { params: { factory_id: factoryId } })
  },
  async command(printer: ThreeDPrinter, action: 'pause' | 'resume', reason: string) {
    const response = await http.post(`${base}/printers/${printer.id}/commands`, {
      factory_id: factoryId,
      action,
      reason,
      idempotency_key: `${action}-${printer.id}-${Date.now()}`,
    })
    return response.data
  },
  async audit(limit = 200) {
    const response = await http.get<ThreeDAuditEvent[]>(`${base}/audit`, {
      params: { factory_id: factoryId, limit },
    })
    return response.data
  },
  async exportWorkbook() {
    const response = await http.get<Blob>(`${base}/export.xlsx`, {
      params: { factory_id: factoryId },
      responseType: 'blob',
      timeout: 30_000,
    })
    return response.data
  },
}
