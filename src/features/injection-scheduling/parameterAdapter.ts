// Presentation-only adapters. Never normalize an untouched value or unknown path.
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };
export function patchJsonPath(
  value: JsonValue,
  path: (string | number)[],
  replacement: JsonValue,
): JsonValue {
  if (!path.length) return replacement;
  const [key, ...tail] = path;
  if (Array.isArray(value)) {
    const copy = [...value];
    copy[Number(key)] = patchJsonPath(
      copy[Number(key)] ?? null,
      tail,
      replacement,
    );
    return copy;
  }
  const copy = value && typeof value === 'object' ? { ...value } : {};
  copy[String(key)] = patchJsonPath(
    copy[String(key)] ?? null,
    tail,
    replacement,
  );
  return copy;
}
export function parseParameter(raw: string, original: unknown): unknown {
  if (typeof original === 'object' || typeof original === 'boolean')
    return JSON.parse(raw);
  if (typeof original === 'number') {
    if (raw.trim() === '' || !Number.isFinite(Number(raw)))
      throw new Error('请填写有效数字');
    return Number(raw);
  }
  return raw;
}
export function numericEntry(
  raw: string,
  original: JsonValue | undefined,
): JsonValue {
  if (raw === '') return null;
  if (!Number.isFinite(Number(raw))) throw new Error('请输入有效数字');
  return typeof original === 'string' ? raw : Number(raw);
}
export function patchWorkingDay(
  value: JsonValue,
  day: number,
  checked: boolean,
): JsonValue {
  const days = Array.isArray(value) ? value : [];
  return checked
    ? days.includes(day)
      ? days
      : [...days, day]
    : days.filter((value) => value !== day);
}
export const objectFields: Record<
  string,
  {
    key: string;
    label: string;
    type: 'number' | 'boolean' | 'list' | 'text' | 'select';
    options?: Record<string, string>;
  }[]
> = {
  defaults: [
    { key: 'gross_weight_g', label: '毛重 g', type: 'number' },
    { key: 'price_per_shot', label: '单啤价格', type: 'number' },
    { key: 'target_shots_per_day', label: '日目标 / 啤', type: 'number' },
    { key: 'net_weight_g', label: '每啤净重 g', type: 'number' },
  ],
  requirements: [
    {
      key: 'machine_family',
      label: '机型',
      type: 'select',
      options: { HORIZONTAL: '卧式', VERTICAL: '立式', TWO_COLOR: '双色专用' },
    },
    {
      key: 'speed_class',
      label: '必须速度等级',
      type: 'select',
      options: { NORMAL: '普通', HIGH_SPEED: '高速', ELECTRIC: '全电' },
    },
    {
      key: 'preferred_speed_class',
      label: '偏好速度等级',
      type: 'select',
      options: { NORMAL: '普通', HIGH_SPEED: '高速', ELECTRIC: '全电' },
    },
    {
      key: 'required_capabilities',
      label: '所需能力编码（每行一个）',
      type: 'list',
    },
    {
      key: 'forbidden_machine_codes',
      label: '禁排机号（每行一个）',
      type: 'list',
    },
    { key: 'manipulator_requirement', label: '机械手要求', type: 'text' },
    { key: 'fixture_requirement', label: '夹具要求', type: 'text' },
  ],
  capabilities: [
    { key: 'CORE_PULL', label: '抽芯', type: 'boolean' },
    { key: 'HEATING', label: '电热', type: 'boolean' },
    { key: 'AUTOMATIC', label: '全自动', type: 'boolean' },
    { key: 'fixtures', label: '可用夹具编码（每行一个）', type: 'list' },
  ],
  restrictions: [
    { key: 'forbidden_resins', label: '禁排树脂（每行一个）', type: 'list' },
    { key: 'only_resin', label: '限定树脂', type: 'text' },
    { key: 'only_grade', label: '限定牌号', type: 'text' },
    { key: 'transparent_only', label: '仅透明产品', type: 'boolean' },
  ],
};
