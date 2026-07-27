import type {
  DataProvenance,
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionPreviewDataset,
  InjectionRuleConfig,
  InjectionScheduleTask,
} from '@/types/injectionSchedule'

/**
 * Local Phase 1 mapping of the 2026-07-21 Huaxing Excel snapshot.
 *
 * This is preview evidence only. It is not a saved, approved, or published
 * production schedule, and it must never be promoted across factory boundaries.
 */
export const INJECTION_PREVIEW_SOURCE: DataProvenance = {
  source: 'workbook_preview',
  confidence: 'verified',
  sourceId: 'huaxing-daily-plan-2026-07-21',
  sourceFileName: '华兴啤机日排版表1.xlsx',
  sourceFileSha256: null,
  sheetName: '计划表',
  sourceRow: null,
  capturedAt: '2026-07-21T00:00:00+08:00',
  importedAt: null,
  importedBy: null,
}

type MachineSourceRow = readonly [
  sourceRow: number,
  machineNo: string,
  machineClass: string,
  speedType: string,
  armLabel: string,
  restriction: string | null,
]

type OrderSourceRow = readonly [
  sourceRow: number,
  machineRequirement: string,
  moldNo: string,
  productName: string,
  orderNo: string,
  itemNo: string,
  orderShots: number,
  producedShots: number,
  outstandingShots: number,
  targetShotsPerDay: number,
  colorName: string,
  colorCode: string | number,
  materialCode: string,
  engineeringNetWeightG: number,
  orderedAt: number | string | null,
  deliveryDueAt: number | string | null,
  armLabel: string,
  fixture: string | null,
  note: string | null,
  pendingBucket: string | null,
]

type ScheduledSourceRow = readonly [
  order: OrderSourceRow,
  machineNo: string,
  startAt: string,
  endAt: string,
]

const HUAXING_FACTORY_ID = 'huaxing'
const BUSINESS_DATE = '2026-07-21'
const PLAN_BASE_AT = '2026-07-21T08:00:00+08:00'
const PLAN_VERSION_ID = 'huaxing-preview-2026-07-21'

const machineSourceRows: readonly MachineSourceRow[] = [
  [4, '旧1', '50A 400T', '普通', '双臂五轴', null],
  [5, '旧2', '32A 320T', '高速', '双臂五轴', '抽芯不行'],
  [13, '旧3', '32A 320T', '高速', '单臂三轴', 'PC螺杆'],
  [16, '旧4', '24A 260T', '高速', '单臂三轴', '高压超160就不行'],
  [17, '旧5', '24A 260T', '高速', '单臂三轴', null],
  [19, '旧6', '24A 260T', '高速', '单臂三轴', null],
  [20, '旧7', '18A 200T', '高速', '单臂三轴', '不可啤PVC'],
  [21, '旧8', '18A 200T', '高速', '单臂三轴', 'PVC螺杆'],
  [23, '旧9', '18A 200T', '高速', '双臂五轴', null],
  [26, '旧38', '7A 120T', '普通', '单臂三轴', 'PVC螺杆'],
  [30, '旧10', '18A 200T', '高速', '双臂五轴', null],
  [32, '旧11', '24A 260T', '高速', '双臂五轴', null],
  [34, '旧12', '12A 150T', '高速', '双臂五轴', '抽芯不行'],
  [39, '旧13', '12A 150T', '高速', '单臂三轴', '不可啤PVC，白色'],
  [40, '旧39', '7A 100T', '全电动机', '单臂三轴', '不可抽芯'],
  [42, '旧14', '14A', '立式（大）', '无', null],
  [44, '旧15', '7A 90T', '立式（小）', '无', null],
  [46, '旧16', '14A 160T', '普通', '双臂五轴', 'PVC螺杆'],
  [52, '旧17', '5A 90T', '普通', '双臂五轴', '螺杆已电镀、PVC'],
  [54, '旧18', '5A 90T', '普通', '双臂五轴', '螺杆已电镀、PVC'],
  [60, '旧19', '5A 90T', '普通', '单臂三轴', '螺杆已电镀、PVC'],
  [62, '旧20', '7A 120T', '普通', '双臂五轴', '螺杆已电镀、PVC'],
  [66, '旧21', '7A 110T', '全电动机', '单臂三轴', '不可抽芯'],
  [70, '旧22', '7A 110T', '全电动机', '单臂三轴', '不可抽芯'],
  [77, '旧23', '7A 110T', '全电动机', '单臂三轴', '不可抽芯'],
  [80, '旧24', '7A 110T', '全电动机', '单臂三轴', '不可抽芯'],
  [88, '旧25', '7A 110T', '全电动机', '单臂三轴', '不可抽芯'],
  [90, '旧26', '14A 160T', '普通', '双臂五轴', 'PVC螺杆'],
  [106, '旧27', '14A 160T', '普通', '双臂五轴', 'PVC螺杆'],
  [109, '旧28', '5A 55T', '全电动机', '单臂三轴', '不可抽芯'],
  [111, '旧29', '80A 800T', '普通机', '双臂五轴', null],
  [113, '旧30', '12A 150T', '高速', '单臂三轴', '抽芯不行'],
  [115, '旧31', '12A 150T', '高速', '双臂五轴', '抽芯不行'],
  [116, '旧32', '24A 260T', '普通', '双臂五轴', '合金螺杆 不可装PVC'],
  [120, '旧33', '35A 350T', '普通', '双臂五轴', '螺杆已电镀、PVC'],
  [121, '旧34', '32A 320T', '普通', '双臂五轴', '合金螺杆'],
  [124, '旧35', '5A 90T', '普通', '双臂五轴', 'PVC螺杆'],
  [128, '旧36', '双色机', '双色机', '双臂五轴', null],
  [131, '旧37', '100A', '普通机', '新型机械手+单臂', null],
  [139, '新1', '60A 500T', '高速', '双臂五轴', null],
  [142, '新2', '32A 320T', '高速', '双臂五轴', 'PC螺杆'],
  [146, '新3', '32A 320T', '高速', '双臂五轴', 'PC螺杆'],
  [148, '新4', '24A 260T', '高速', '双臂五轴', null],
  [151, '新5', '24A 260T', '高速', '双臂五轴', null],
  [156, '新6', '24A 260T', '高速', '单臂三轴', '机器不稳定'],
  [158, '新7', '24A 260T', '高速', '单臂三轴', '螺杆已电镀、PVC'],
  [160, '新8', '24A 260T', '高速', '单臂三轴', '抽芯不行'],
  [166, '新9', '24A 260T', '高速', '单臂三轴', null],
  [174, '新10', '18A 200T', '普通', '双臂五轴', 'PVC螺杆'],
  [178, '新11', '18A 200T', '高速', '单臂三轴', null],
  [181, '新12', '18A 200T', '高速', '双臂五轴', '只可以啤PMMA MF-001'],
  [190, '新13', '18A 200T', '高速', '单臂三轴', '只可以啤透明的'],
  [194, '新14', '18A 200T', '高速', '双臂五轴', '只可以啤PMMA MF-001'],
  [197, '新15', '18A 200T', '高速', '单臂三轴', null],
  [203, '新16', '18A 200T', '高速', '单臂三轴', null],
  [206, '新17', '18A 200T', '高速', '双臂五轴', null],
  [211, '新18', '18A 200T', '高速', '单臂三轴', 'ABS不好啤'],
  [213, '新19', '18A 200T', '高速', '双臂五轴', '双臂五轴'],
  [216, '新20', '18A 200T', '高速', '单臂三轴', null],
  [219, '新21', '12A 150T', '高速', '单臂三轴', '抽芯不行'],
  [234, '新22', '12A 150T', '高速', '单臂三轴', null],
  [236, '新23', '12A 150T', '高速', '单臂三轴', '可以啤PVC'],
  [242, '新24', '12A 150T', '高速', '单臂三轴', null],
  [251, '新25', '12A 150T', '高速', '双臂五轴', null],
  [256, '新26', '12A 150T', '高速', '单臂三轴', null],
  [264, '新27', '12A 150T', '高速', '双臂五轴', null],
  [280, '新28', '12A 150T', '高速', '双臂五轴', null],
  [284, '新29', '14A 180T', '全电动机', '双臂五轴', '不可抽芯'],
  [289, '新30', '12A 150T', '高速', '单臂三轴', '可以啤PVC'],
  [293, '新31', '12A 150T', '高速', '双臂五轴', '装抽芯抽不了'],
  [297, '新32', '12A 150T', '高速', '单臂三轴', '啤PVC好一点'],
  [309, '新33', '5A 55T', '全电动机', '单臂三轴', '不可抽芯'],
  [311, '新34', '12A 130T', '全电动机', '单臂三轴', '不可抽芯'],
  [317, '新35', '12A 150T', '高速', '双臂五轴', null],
  [326, '新36', '5A 50T', '全电动机', '双臂五轴', '不可抽芯'],
  [331, '新37', '5A 50T', '全电动机', '单臂三轴', '不可抽芯'],
]

/**
 * Cached rows classified as genuinely unscheduled: row 350 plus rows >= 352
 * whose 欠数 (N) is positive and whose 机号 (B) is not a valid 旧1..旧39 /
 * 新1..新37 machine id. Deliberately no task or planned timestamp is created
 * for these rows, so the domain representation remains truly unscheduled.
 */
const pendingSourceRows: readonly OrderSourceRow[] = [
  [350, '5A双', 'T01-BL006-00300000', '小杯盖', 'BJB251268', 'F12-BL028', 756, 0, 756, 3200, '泥黄色', 71484, 'ABS KF-740', 9.4, 46213, 46239, '单臂', '吸盘', null, '色粉待定'],
  [352, '7A模小/压力大', '20 383 4001-002', '冲浪板架/船桨', 'BJB251280', '20 383 7021', 2700, 0, 2700, 3400, '灰色', 89738, '1#PP AV161', 18, 46221, 46251, '单臂', '吸盘', '堵啤', null],
  [353, '14A', '20 383 4005-004-1', '包装扣/房车包装支架', 'BJB251280', '20 383 7021', 5400, 0, 5400, 4000, '灰色', 89738, '1#PP AV161', 9.8, 46221, 46251, '单臂', '吸盘', '堵啤吉普车包装支架、后尾扣', null],
  [354, '5A', '20 383 4005-005', '公仔支架', 'BJB251280', '20 383 7021', 1350, 0, 1350, 4400, '黑色', '黑种', 'HDPE 5502BN+LDPE 160AT(3:1)', 13.2, 46221, 46251, '单臂', '夹子', null, null],
  [355, '5A', '20 330 2028-010', '水箱塞', 'BJB251282', '20 330 2028', 375, 0, 375, 4800, '黑色', '黑种', 'LDPE 160AT', 3.6, 46221, 46251, '单臂', '吸盘', null, null],
  [356, '14A两边抽芯', '20 383 5003-003', '自行车-支撑架', 'BJB251280', '20 383 7021', 2700, 0, 2700, 3600, '蓝色', 92956, '1#PP AV161', 5.6, 46221, 46251, '单臂', '夹子', null, null],
  [357, '7A', '20 383 6004-008', '驾驶室座椅/沙发座椅/床', 'BJB251280', '20 383 7021', 5400, 0, 5400, 3800, '米黄色', 93030, '1#PP AV161', 24.5, 46221, 46251, '单臂', '吸盘', null, null],
  [358, '7A', '20 383 8001-005-1', '座椅-前后架', 'BJB251280', '20 383 7021', 2700, 0, 2700, 3800, '深黄色', 44704, '1#PP AV161', 6.94, 46221, 46251, '单臂', '夹子', '堵住围栏啤货', null],
  [360, '7A', '20 330 7003-03', '车身内笼', 'BJB251285', '20 330 7003', 3000, 0, 3000, 3200, '灰色', 45431, '1#PP AV161', 74, 46221, 46251, '单臂', '吸盘', null, null],
  [361, '7A.胶量重', '20 330 2049-006', '车底/电池门/脚踏*2', 'BJB251286', '20 330 2053', 2970, 0, 2970, 3800, '灰色', 44603, '1#PP AV161', 68.2, 46221, 46251, '单臂', '吸盘', null, null],
  [362, '4A', '20 330 2049-002', '车窗/压盖', 'BJB251286', '20 330 2053', 2970, 0, 2970, 4000, '银色', 86262, '1#PP AV161', 10.4, 46221, 46251, '单臂', '吸盘', null, null],
  [363, '7A', '20 374 2018-003', '垃圾车车厢/后门', 'BJB251283', '20 374 2018', 3000, 0, 3000, 3600, '橙色', 49956, '1#PP AV161', 20.6, 46221, 46251, '单臂', '吸盘', null, null],
  [364, '7A', '20 374 2018-004', '车厢内件/底板/压件', 'BJB251283', '20 374 2018', 1500, 0, 1500, 3800, '橙色', 49956, '1#PP AV161', 29.2, 46221, 46251, '单臂', '夹子', null, null],
  [365, '7A', '20 330 7003-08', '担架床/医疗盒/包装扣*2', 'BJB251285', '20 330 7003', 1500, 0, 1500, 4000, '橙色', 46030, '1#PP AV161', 42, 46221, 46251, '单臂', '吸盘', null, null],
  [366, '5A', '20 330 2049-003', '汉堡大身', 'BJB251286', '20 330 2053', 2970, 0, 2970, 3600, '橙色', 49226, '1#PP AV161', 25, 46221, 46251, '单臂', '吸盘', null, null],
  [367, '5A', '20 330 7003-06', '车铃盖*4', 'BJB251285', '20 330 7003', 3000, 0, 3000, 4600, '黄色', 46029, '1#PP AV161', 20, 46221, 46251, '单臂', '吸盘', null, null],
  [368, '5A', '20 330 7003-07', '无人机/担架左右脚/担架轮*2/担架绑带/按制/喇叭盖', 'BJB251285', '20 330 7003', 3000, 0, 3000, 3800, '黄色', 46029, '1#PP AV161', 20.9, 46221, 46251, '单臂', '吸盘', null, null],
  [369, '7A', '20 330 2038-001', '车厢/侧门/底板/包装扣*2', 'BJB251286', '20 330 2053', 5940, 0, 5940, 4200, '黄色', 48108, '1#PP AV161', 45.3, 46221, 46251, '单臂', '吸盘', null, null],
  [370, '5A', '20 330 2029-002', '小垃圾车车头', 'BJB251286', '20 330 2053', 2970, 0, 2970, 4400, '黄色', 48108, '1#PP AV161', 17.2, 46221, 46251, '单臂', '吸盘', null, null],
  [371, '5A', '20 330 2029-002', '小垃圾车车头', 'BJB251286', '20 330 2053', 2970, 0, 2970, 4400, '白色', 44599, '1#PP AV161', 17.2, 46221, 46251, '单臂', '吸盘', null, null],
  [372, '5A', '20 330 2049-004', '汉堡内笼透明件/顶灯/标志件', 'BJB251286', '20 330 2053', 2970, 0, 2970, 3800, '透明黄', 49371, 'PP SM198', 34.2, 46221, 46251, '单臂', '吸盘', null, null],
  [373, '7A模小/胶量大', '20 330 2048-001', '车斗', 'BJB251286', '20 330 2053', 2970, 0, 2970, 4000, '蓝色', 49224, '1#PP AV161', 40.4, 46221, 46251, '单臂', '吸盘', null, null],
  [374, '5A', '20 330 2049-005', '汉堡内装饰件/车尾架', 'BJB251286', '20 330 2053', 2970, 0, 2970, 4000, '绿色', 49225, '1#PP AV161', 30.8, 46221, 46251, '单臂', '吸盘', null, null],
  [376, '7A', '20 371 2023-005', '车底', 'BJB251169', '20 371 2023', 2100, 0, 2100, 3600, '黑色', '黑色', '1#PP AV161', 45, 46151, 46181, '单臂', '吸盘', null, null],
  [377, '7A', '20 371 2023-005', '车底', 'BJB251253', '20 374 2019', 1500, 0, 1500, 3600, '黑色', '黑色', '1#PP AV161', 45, 46189, 46216, '单臂', '吸盘', null, null],
  [378, '5A', '20 375 1010-015', '车身', '华康A补数', '20 375 1010-3', 4620, 0, 4620, 3800, '黑色', '黑种', '1#PP AV161', 25.6, 46101, 46129, '单臂', '吸盘', null, null],
  [380, '12A', 'BBT 20230926-01-A', '平头子弹头', 'BJB251273', '45841', 1141, 0, 1141, 2600, '蓝色', 47687, 'TPE GP510-3001', 36.8, 46217, 46241, '单臂', '一个气剪', '有复模，堵啤', null],
  [384, '5A', 'PAMT-10M-01', '小海龟上盖', '啤机补数', '9560', 750, 0, 750, 4000, '珠光红/906C', 49101, '透明ABS TR557 INP', 4.8, 46185, 46256, '单臂', '斗盘', null, null],
  [386, '14A要双臂', 'BBT 36100-04', '水樽盖', 'BJB251287', '36230', 84, 0, 84, 4000, '深橙色', 91906, 'LDPE 160AT', 12.6, 46223, 46228, '单臂', '吸盘', null, null],
  [387, '7A', 'BBT 36100-05', '泵身', 'BJB251287', '36230', 63, 0, 63, 4000, '原色', '原色', 'ABS 750NSW', 14.88, 46223, 46228, '单臂', '夹子', null, null],
  [388, '14A', 'BBT 36100-06', '泵底', 'BJB251287', '36230', 32, 0, 32, 4400, '原色', '原色', 'LDPE 160AT', 26.88, 46223, 46228, '单臂', '夹子', null, null],
  [389, '7A（装电机）半自动', 'BBT 36100-07-B', '出水弯头B', 'BJB251287', '36230', 63, 0, 63, 3600, '原色', '原色', 'ABS 750NSW', 5.44, 46223, 46228, '半自动', '夹子', null, null],
  [390, '5A', 'BBT 36100-08', '入水弯头', 'BJB251287', '36230', 32, 0, 32, 4500, '原色', '原色', 'ABS 750NSW', 7.36, 46223, 46228, '单臂', '夹子', null, null],
  [391, '5A双半自动', 'BBT 36100-10', '活塞', 'BJB251287', '36230', 32, 0, 32, 4500, '原色', '原色', 'TPR 35度（本白）+TPR 65度（本白）（5:5）', 4.8, 46223, 46228, '半自动', '半自动', null, null],
]

const scheduledSourceRows: readonly ScheduledSourceRow[] = [
  [[6, '32A双电热（模高）', 'GT1214', '自卸车、消防车车轮/座椅', 'FFD442145', 'DTK01R', 3528, 3410, 118, 1400, '黑色', '黑种', 'PP 5100NA', 379, 46213, '2026-07-24 00:00:00', '双臂', '吸盘', null, null], '旧2', '2026-07-21 10:06:20', '2026-07-21 12:07:42.286000'],
  [[14, '32A模小/长', 'PAMT-01M-01', '水箱', 'BJB250791', '9560', 30000, 23765, 6235, 1400, '透明', '透明', 'PC HS152R', 384, 46034, 46178, '单臂', '吸盘', '有复模', null], '旧3', '2026-07-21 10:06:20', '2026-07-25 20:59:28.571000'],
  [[24, '14A', 'MNVN-19M-06', '包装底座', 'DG002', '77794', 100000, 12210, 87790, 3800, '黄色', 63175, '1#PP AV161', 55.45, 46193, 46258, '双臂', '吸盘', null, null], '旧9', '2026-07-21 10:06:20', '2026-08-13 12:34:07.368000'],
  [[27, '7A半自动', 'JP45801-24-1', '喷油，草莓熊转水口啤LOTSO 靴子左/LOTSO 靴子右', 'E260707-05', '45801/45801W2/45801W3', 3800, 2170, 1630, 2500, '237C/紫红色', 47825, 'PVC 60度（透明）', 8.2, 46211, '2026-07-21 00:00:00', '半自动', '吸盘', '签板（喷油）', null], '旧38', '2026-07-21 10:06:20', '2026-07-22 01:45:12.800000'],
  [[33, '14A', 'MNVN-19M-05', '包装底座', 'DG002', '77794', 100000, 11395, 88605, 3800, '黄色', 63175, '1#PP AV161', 55.45, 46193, 46258, '双臂', '吸盘', null, null], '旧11', '2026-07-21 10:06:20', '2026-08-13 17:42:57.895000'],
  [[35, '7A', 'BBT 45849-03', '枪顶左右盖', 'BJB251273', '45841', 1901, 100, 1801, 4000, '蓝色', 44440, 'ABS KF-740', 44, 46217, 46241, '单臂', '吸盘', null, null], '旧12', '2026-07-21 10:06:20', '2026-07-21 20:54:41.600000'],
  [[140, '32A电热', '20 330 7003-02', '车身', 'BJB251285', '20 330 7003', 3000, 0, 3000, 2800, '白色', 46395, '1#PP JM350', 142, 46221, 46251, '单臂', '吸盘', null, null], '新1', '2026-07-21 10:06:20', '2026-07-22 11:49:11.429000'],
  [[143, '32A模小/长', 'PAMT-01M-01', '水箱', 'BJB251103', '9560', 50000, 22900, 27100, 1400, '透明', '透明', 'PC HS152R', 384, 46136, 46178, '单臂', '吸盘', '有复模', null], '新2', '2026-07-21 10:06:20', '2026-08-09 18:40:37.143000'],
  [[147, '32A模小/长', 'PAMT-01M-01', '水箱', 'BJB251203', '9560', 80000, 26435, 53565, 1400, '透明', '透明', 'PC HS152R', 384, 46168, 46198, '单臂', '吸盘', '有复模', null], '新3', '2026-07-21 10:06:20', '2026-08-28 16:21:45.714000'],
  [[149, '24A双', 'BBT 40210-01', '转盘枪-左枪身', 'BJB251215', '40211', 42105, 39650, 2455, 2800, '金属色', 49297, 'MABS CT2010', 164.5, 46174, 46198, '双臂', '吸盘', null, null], '新4', '2026-07-21 10:06:20', '2026-07-22 07:08:54.286000'],
  [[152, '18A模小/长', 'T01-JS002-00200000', '磅秤上下身', 'BJB251275', 'F12-JS002-C0050000', 3010, 860, 2150, 2200, '浅蓝', 49404, 'ABS KF-740', 77.5, 46217, 46227, '单臂', '吸盘', null, null], '新5', '2026-07-21 10:06:20', '2026-07-22 09:33:36.364000'],
  [[161, '18A模小/压力大', 'T01-BL201-00100000', '上盖/反射鏡座', 'BJB251274', 'BL010', 3010, 1180, 1830, 2000, '蓝色', 48909, 'ABS KF-740', 99.4, 46217, 46227, '单臂', '吸盘', null, null], '新8', '2026-07-21 10:06:20', '2026-07-22 08:03:56'],
]

function provenanceForRow(sourceRow: number): DataProvenance {
  return {
    ...INJECTION_PREVIEW_SOURCE,
    sourceRow,
  }
}

function machineId(machineNo: string) {
  const workshop = machineNo.startsWith('旧') ? 'old' : 'new'
  const sequence = machineNo.match(/\d+/)?.[0] ?? machineNo
  return `huaxing-machine-${workshop}-${sequence}`
}

function moldId(moldNo: string) {
  const safeCode = moldNo
    .trim()
    .toLocaleLowerCase('en-US')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `huaxing-mold-${safeCode}`
}

function armTypeFromLabel(label: string): InjectionMachine['armType'] {
  if (label.includes('双臂')) return 'double'
  if (label.includes('单臂')) return 'single'
  return 'none'
}

function orderArmRequirement(
  machineRequirement: string,
  armLabel: string,
): InjectionOrder['armRequirement'] {
  if (machineRequirement.includes('要双臂')) return 'double'
  if (armLabel.includes('半自动')) return null
  return armTypeFromLabel(armLabel)
}

function tonnageFromClass(machineClass: string) {
  const match = machineClass.match(/(\d+)\s*T/i)
  return match ? Number(match[1]) : null
}

function screwTypeFromRestriction(restriction: string | null) {
  if (!restriction) return null
  if (restriction.includes('合金螺杆')) return 'alloy'
  if (restriction.includes('PC螺杆')) return 'PC'
  if (restriction.includes('螺杆已电镀')) return 'plated-PVC'
  if (restriction.includes('PVC螺杆')) return 'PVC'
  return null
}

function materialRulesFromRestriction(
  machineNo: string,
  restriction: string | null,
): InjectionMachine['materialRules'] {
  if (!restriction) return null
  if (restriction.includes('不可啤PVC') || restriction.includes('不可装PVC')) {
    return [{
      id: `${machineId(machineNo)}-deny-pvc`,
      mode: 'deny',
      materialCodes: ['PVC'],
      reason: `计划表机头备注：${restriction}`,
    }]
  }
  if (restriction.includes('只可以啤PMMA MF-001')) {
    return [{
      id: `${machineId(machineNo)}-pmma-only`,
      mode: 'allow_only',
      materialCodes: ['PMMA MF-001'],
      reason: `计划表机头备注：${restriction}`,
    }]
  }
  return null
}

function normalizeWorkbookDate(value: number | string | null) {
  if (value == null) return null
  if (typeof value === 'number') {
    // Ignore time-only / 1900-era formula artifacts. Real workbook dates in
    // this snapshot are modern Excel serials around 46,000.
    if (!Number.isFinite(value) || value < 20_000) return null
    const utcDate = new Date(Date.UTC(1899, 11, 30) + Math.floor(value) * 86_400_000)
    return `${utcDate.toISOString().slice(0, 10)}T00:00:00+08:00`
  }

  const match = value.trim().match(
    /^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?/,
  )
  if (!match || Number(match[1].slice(0, 4)) < 2000) return null
  return `${match[1]}T${match[2] ?? '00:00:00'}+08:00`
}

function colorRank(colorName: string) {
  if (/透明/.test(colorName)) return 0
  if (/原色|白色|银色/.test(colorName)) return 1
  if (/浅|米黄|泥黄/.test(colorName)) return 2
  if (/黄|橙|红/.test(colorName)) return 3
  if (/蓝|绿|灰|金属|紫/.test(colorName)) return 4
  if (/黑|深/.test(colorName)) return 5
  return null
}

function priorityFromDueDate(deliveryDueAt: string | null): InjectionOrder['priority'] {
  if (!deliveryDueAt) return 'P2'
  const dueTime = Date.parse(deliveryDueAt)
  const baseTime = Date.parse(PLAN_BASE_AT)
  const days = (dueTime - baseTime) / 86_400_000
  if (days <= 0) return 'P0'
  if (days <= 7) return 'P1'
  if (days <= 28) return 'P2'
  return 'P3'
}

function capabilitiesFromRequirement(
  machineRequirement: string,
): InjectionOrder['capabilitiesRequired'] {
  if (machineRequirement.includes('两边抽芯')) return ['double_core_pull']
  if (machineRequirement.includes('抽芯')) return ['core_pull']
  return []
}

function createOrder(source: OrderSourceRow, pending: boolean): InjectionOrder {
  const [
    sourceRow,
    machineRequirement,
    sourceMoldNo,
    productName,
    orderNo,
    itemNo,
    orderShots,
    producedShots,
    outstandingShots,
    targetShotsPerDay,
    sourceColorName,
    sourceColorCode,
    materialCode,
    ,
    sourceOrderedAt,
    sourceDeliveryDueAt,
    armLabel,
    fixture,
    note,
    pendingBucket,
  ] = source
  const deliveryDueAt = normalizeWorkbookDate(sourceDeliveryDueAt)
  const priority = priorityFromDueDate(deliveryDueAt)
  const flags = [
    `机型要求来自计划表自由文本：${machineRequirement}`,
    ...(pending ? ['Excel 待排记录：未生成计划开始/完成时间'] : []),
    ...(pendingBucket ? [`待排分类：${pendingBucket}`] : []),
    ...(note ? [`计划表备注：${note}`] : []),
    ...(armLabel.includes('半自动') ? ['机械手字段为半自动，需人工确认结构化能力'] : []),
    '毛重未提供；净重保留在关联模具工程净重字段',
  ]

  return {
    id: `huaxing-order-row-${sourceRow}`,
    factoryId: HUAXING_FACTORY_ID,
    orderNo,
    itemNo,
    moldId: moldId(sourceMoldNo),
    productName,
    orderShots,
    producedShots,
    outstandingShots,
    targetShotsPerDay,
    grossShotWeightG: null,
    colorName: sourceColorName,
    colorCode: String(sourceColorCode),
    colorRank: colorRank(sourceColorName),
    materialCode,
    armRequirement: orderArmRequirement(machineRequirement, armLabel),
    fixtureRequirements: fixture ? [fixture] : [],
    capabilitiesRequired: capabilitiesFromRequirement(machineRequirement),
    orderedAt: normalizeWorkbookDate(sourceOrderedAt),
    deliveryStartAt: null,
    deliveryDueAt,
    warehouseBufferHours: 72,
    downstreamBufferHours: 0,
    downstreamProcess: note?.includes('喷油') || productName.includes('喷油')
      ? '喷油'
      : null,
    downstreamUrgency: priority === 'P0' ? 1 : priority === 'P1' ? 0.8 : 0.5,
    priority,
    dataQualityFlags: flags,
    sourceWorkbookRow: sourceRow,
    provenance: provenanceForRow(sourceRow),
  }
}

const scheduledOrders = scheduledSourceRows.map(([source]) => createOrder(source, false))
const pendingOrders = pendingSourceRows.map((source) => createOrder(source, true))
const huaxingOrders: InjectionOrder[] = [...scheduledOrders, ...pendingOrders]

const allOrderSourceRows: readonly OrderSourceRow[] = [
  ...scheduledSourceRows.map(([source]) => source),
  ...pendingSourceRows,
]

const huaxingMolds: InjectionMold[] = []
const seenMoldIds = new Set<string>()
for (const source of allOrderSourceRows) {
  const [
    sourceRow,
    machineRequirement,
    sourceMoldNo,
    productName,
    ,
    ,
    ,
    ,
    ,
    targetShotsPerDay,
    sourceColorName,
    ,
    materialCode,
    engineeringNetWeightG,
    ,
    ,
    armLabel,
    fixture,
  ] = source
  const id = moldId(sourceMoldNo)
  if (seenMoldIds.has(id)) continue
  seenMoldIds.add(id)

  huaxingMolds.push({
    id,
    factoryId: HUAXING_FACTORY_ID,
    moldNo: sourceMoldNo,
    name: productName,
    recommendedMachineClass: machineRequirement,
    minTonnage: null,
    grossShotWeightG: null,
    engineeringNetWeightG,
    lengthMm: null,
    widthMm: null,
    heightMm: null,
    moldThicknessMm: null,
    requiredOpeningStrokeMm: null,
    requiredEjectorClearanceMm: null,
    moldWeightKg: null,
    armRequirement: orderArmRequirement(machineRequirement, armLabel) ?? 'none',
    fixtureRequirements: fixture ? [fixture] : [],
    capabilitiesRequired: capabilitiesFromRequirement(machineRequirement),
    materialCode,
    requiredScrewTypes: [],
    defaultColor: sourceColorName,
    defaultColorRank: colorRank(sourceColorName),
    cavityCount: null,
    standardCycleSeconds: targetShotsPerDay > 0
      ? Math.round((86_400 / targetShotsPerDay) * 100) / 100
      : null,
    dataQualityFlags: [
      `机型要求来自计划表自由文本：${machineRequirement}`,
      '模具尺寸、模厚、开模行程、顶出间隙及模重待工程主数据确认',
      '计划表 T 列为净重；毛重未提供',
    ],
    provenance: provenanceForRow(sourceRow),
  })
}

const scheduledMachineEndByNo = new Map(
  scheduledSourceRows.map(([, sourceMachineNo, , endAt]) => [
    sourceMachineNo,
    normalizeWorkbookDate(endAt),
  ]),
)

const huaxingMachines: InjectionMachine[] = machineSourceRows
  .map(([
    sourceRow,
    sourceMachineNo,
    machineClass,
    speedType,
    armLabel,
    restriction,
  ]): InjectionMachine => {
    const tonnage = tonnageFromClass(machineClass)
    const schedulingLocked = restriction === '机器不稳定'
    const availableFrom = scheduledMachineEndByNo.get(sourceMachineNo) ?? null
    return {
      id: machineId(sourceMachineNo),
      factoryId: HUAXING_FACTORY_ID,
      workshop: sourceMachineNo.startsWith('旧') ? 'old' : 'new',
      machineNo: sourceMachineNo,
      machineClass,
      tonnage,
      speedType,
      armType: armTypeFromLabel(armLabel),
      supportedFixtures: null,
      screwType: screwTypeFromRestriction(restriction),
      capabilities: machineClass === '双色机' ? ['two_color'] : null,
      materialRules: materialRulesFromRestriction(sourceMachineNo, restriction),
      maxShotWeightG: null,
      tieBarWidthMm: null,
      tieBarHeightMm: null,
      minMoldThicknessMm: null,
      maxMoldThicknessMm: null,
      maxOpeningStrokeMm: null,
      maxEjectorClearanceMm: null,
      status: schedulingLocked ? 'locked' : availableFrom ? 'running' : 'idle',
      schedulingLocked,
      availableFrom,
      unavailableWindows: [],
      dataCompleteness: tonnage == null ? 0.35 : 0.45,
      dataQualityFlags: [
        '机台空间、射胶能力、模厚及行程参数待工程确认',
        ...(restriction ? [`计划表机头备注：${restriction}`] : []),
      ],
      provenance: provenanceForRow(sourceRow),
    }
  })
  .sort((left, right) => {
    const workshopDifference = left.workshop === right.workshop
      ? 0
      : left.workshop === 'old' ? -1 : 1
    if (workshopDifference !== 0) return workshopDifference
    return Number(left.machineNo.match(/\d+/)?.[0] ?? 0)
      - Number(right.machineNo.match(/\d+/)?.[0] ?? 0)
  })

const zeroScoreBreakdown: InjectionScheduleTask['scoreBreakdown'] = {
  dueUrgency: 0,
  sameMoldMaterial: 0,
  setupCost: 0,
  colorTransition: 0,
  loadBalance: 0,
  downstreamImpact: 0,
  exactMatch: 0,
  splitPenalty: 0,
  specialHandlingPenalty: 0,
}

const orderBySourceRow = new Map(
  huaxingOrders.map((order) => [order.sourceWorkbookRow, order]),
)

const huaxingTasks: InjectionScheduleTask[] = scheduledSourceRows.map(
  ([source, sourceMachineNo, sourceStartAt, sourceEndAt]) => {
    const sourceRow = source[0]
    const order = orderBySourceRow.get(sourceRow)
    if (!order) {
      throw new Error(`Missing preview order for workbook row ${sourceRow}`)
    }
    const startAt = normalizeWorkbookDate(sourceStartAt)
    const endAt = normalizeWorkbookDate(sourceEndAt)
    if (!startAt || !endAt) {
      throw new Error(`Invalid scheduled preview timestamp at workbook row ${sourceRow}`)
    }

    return {
      id: `huaxing-task-row-${sourceRow}`,
      planVersionId: PLAN_VERSION_ID,
      factoryId: HUAXING_FACTORY_ID,
      machineId: machineId(sourceMachineNo),
      orderId: order.id,
      startAt,
      endAt,
      plannedShots: order.outstandingShots,
      setupMinutesBefore: 0,
      setupReason: ['Excel 快照代表任务；Phase 1 未重新计算换模/转色时间'],
      score: null,
      scoreBreakdown: { ...zeroScoreBreakdown },
      constraintSnapshot: [],
      source: 'manual',
      locked: false,
      status: 'draft',
      provenance: provenanceForRow(sourceRow),
    }
  },
)

function createRuleConfig(factoryId: string): InjectionRuleConfig {
  return {
    factoryId,
    shotSafetyFactor: 0.8,
    lossRate: 0.01,
    schedulableMachineStatuses: ['idle', 'running', 'setup'],
    setup: {
      firstTaskSetupMinutes: 60,
      sameMoldChangeMinutes: 0,
      differentMoldChangeMinutes: 90,
      sameMaterialChangeMinutes: 0,
      differentMaterialChangeMinutes: 45,
      sameColorChangeMinutes: 0,
      lightToDarkColorMinutes: 25,
      darkToLightColorMinutes: 60,
      unknownColorTransitionMinutes: 60,
      colorTransitionMatrix: [],
      materialTransitionMatrix: [],
    },
    scoring: {
      weights: {
        dueUrgency: 35,
        sameMoldMaterial: 15,
        setupCost: 15,
        colorTransition: 10,
        loadBalance: 10,
        downstreamImpact: 10,
        exactMatch: 5,
        splitPenalty: -12,
        specialHandlingPenalty: -10,
      },
      dueUrgencyHorizonHours: 168,
      setupCostCeilingMinutes: 240,
      colorTransitionCeilingMinutes: 120,
    },
  }
}

const huaxingPreviewDataset: InjectionPreviewDataset = {
  mode: 'preview',
  publishable: false,
  id: PLAN_VERSION_ID,
  factoryId: HUAXING_FACTORY_ID,
  businessDate: BUSINESS_DATE,
  planBaseAt: PLAN_BASE_AT,
  provenance: INJECTION_PREVIEW_SOURCE,
  machines: huaxingMachines,
  molds: huaxingMolds,
  orders: huaxingOrders,
  tasks: huaxingTasks,
  recommendations: {},
  ruleConfig: createRuleConfig(HUAXING_FACTORY_ID),
  dataQualityFlags: [
    '2026-07-21 Excel 快照预览，非保存或发布计划',
    '76 台机头轮廓来自计划表缓存行；关键能力参数仍待工程确认',
    '34 条待排记录没有生成计划开始/完成时间',
    '12 条已排代表任务仅用于 Phase 1 时间轴预览',
    'Excel 中的 1900 年公式时间伪值未进入预览数据',
  ],
}

function createEmptyDataset(factoryId: string): InjectionPreviewDataset {
  const provenance: DataProvenance = {
    source: 'system',
    confidence: 'verified',
    sourceId: `no-injection-preview:${factoryId}`,
    sourceFileName: null,
    sourceFileSha256: null,
    sheetName: null,
    sourceRow: null,
    capturedAt: null,
    importedAt: null,
    importedBy: null,
  }

  return {
    mode: 'preview',
    publishable: false,
    id: `${factoryId}-injection-preview-empty`,
    factoryId,
    businessDate: BUSINESS_DATE,
    planBaseAt: PLAN_BASE_AT,
    provenance,
    machines: [],
    molds: [],
    orders: [],
    tasks: [],
    recommendations: {},
    ruleConfig: createRuleConfig(factoryId),
    dataQualityFlags: ['当前厂区没有注塑排产预览快照'],
  }
}

export const injectionPreviewByFactory: Readonly<Record<string, InjectionPreviewDataset>> = {
  huaxing: huaxingPreviewDataset,
  'huakang-a': createEmptyDataset('huakang-a'),
  'huakang-b': createEmptyDataset('huakang-b'),
  huadeng: createEmptyDataset('huadeng'),
}

function cloneDataset(dataset: InjectionPreviewDataset): InjectionPreviewDataset {
  return JSON.parse(JSON.stringify(dataset)) as InjectionPreviewDataset
}

export function getInjectionPreviewDataset(factoryId: string): InjectionPreviewDataset {
  const dataset = injectionPreviewByFactory[factoryId] ?? createEmptyDataset(factoryId)
  return cloneDataset(dataset)
}
