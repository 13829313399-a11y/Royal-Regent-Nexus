// Material selection and tray details can arrive in separate MQTT reports.
const materialState = Symbol('materialState');

export function cleanText(value, limit = 512) {
  if (typeof value !== 'string') return '';
  return value.replace(/[\uFFFD\uD800-\uDFFF\u0000-\u001F\u007F-\u009F]/g, '').slice(0, limit);
}

export function normalizeState(value) {
  const aliases = { PRINTING: 'RUNNING', PREPARE: 'RUNNING', PREPARING: 'RUNNING',
    PAUSED: 'PAUSE', COMPLETE: 'FINISH', COMPLETED: 'FINISH', READY: 'IDLE' };
  const state = typeof value === 'string' ? value.toUpperCase() : 'UNKNOWN';
  return aliases[state] || (['RUNNING', 'PAUSE', 'FINISH', 'IDLE', 'FAILED', 'ERROR'].includes(state) ? state : 'UNKNOWN');
}

export function initialStatus() {
  return { connected: false, state: 'UNKNOWN', current_file: '', device_job_key: '',
    progress_percent: 0, remaining_minutes: 0, live_material: '', nozzle_temperature: 0,
    bed_temperature: 0, nozzle_target: 0, bed_target: 0, observed_at: '', error_code: '', layer_num: 0, total_layers: 0 };
}

export function mergeReport(previous, report, observedAt) {
  if (!report || Array.isArray(report) || typeof report !== 'object') throw new Error('invalid_print_report');
  const changedJob = report.subtask_id !== undefined && cleanText(String(report.subtask_id), 128) !== previous.device_job_key;
  const state = { ...(changedJob ? initialStatus() : previous), connected: true, observed_at: observedAt };
  if (report.gcode_state !== undefined) state.state = normalizeState(report.gcode_state);
  if (report.subtask_name !== undefined || report.gcode_file !== undefined)
    state.current_file = cleanText(report.subtask_name ?? report.gcode_file);
  // Filenames are not stable job identity. Absent firmware identity stays unproven.
  if (report.subtask_id !== undefined) state.device_job_key = cleanText(String(report.subtask_id), 128);
  /** @type {Record<string, [string, number]>} */
  const fields = { mc_percent: ['progress_percent', 100], mc_remaining_time: ['remaining_minutes', 100000],
    nozzle_temper: ['nozzle_temperature', 500], bed_temper: ['bed_temperature', 200],
    nozzle_target_temper: ['nozzle_target', 500], bed_target_temper: ['bed_target', 200],
    layer_num: ['layer_num', 100000], total_layer_num: ['total_layers', 100000] };
  for (const [key, [target, max]] of Object.entries(fields)) {
    if (report[key] === undefined) continue;
    if (!['number', 'string'].includes(typeof report[key]) || !Number.isFinite(Number(report[key]))) throw new Error('invalid_report_number');
    state[target] = Math.max(0, Math.min(max, Number(report[key])));
  }
  if (report.print_error !== undefined) {
    const code = cleanText(String(report.print_error), 64);
    state.error_code = code === '0' ? '' : code;
  }
  // Physical spool metadata survives job changes, but resets with the MQTT session.
  const material = { ...previous[materialState], trays: { ...previous[materialState]?.trays } };
  if (report.ams?.tray_now !== undefined) material.current = String(report.ams.tray_now);
  if (report.vt_tray?.tray_type !== undefined) material.external = cleanText(report.vt_tray.tray_type, 255);
  for (const unit of Array.isArray(report.ams?.ams) ? report.ams.ams : []) {
    for (const tray of Array.isArray(unit?.tray) ? unit.tray : []) {
      if (tray?.tray_type !== undefined)
        material.trays[Number(unit.id) * 4 + Number(tray.id)] = cleanText(tray.tray_type, 255);
    }
  }
  // 254 selects the external spool; 255 means no selected tray.
  if (material.current !== undefined)
    state.live_material = material.current === '254' ? (material.external ?? '')
      : material.current === '255' ? '' : (material.trays[material.current] ?? '');
  state[materialState] = material;
  return state;
}
