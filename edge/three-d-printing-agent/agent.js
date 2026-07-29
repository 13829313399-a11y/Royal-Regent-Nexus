"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const tls = require("node:tls");

const VERSION = "1.0.0";
const CONFIG_PATH = path.join(__dirname, "config.json");
const MAX_MQTT_BUFFER_BYTES = 1024 * 1024;
const adapters = new Map();
let shuttingDown = false;
let lastCloudError = "";

function loadConfig() {
  if (!fs.existsSync(CONFIG_PATH)) {
    throw new Error(
      `缺少 ${CONFIG_PATH}；请复制 config.example.json 为 config.json 并填写本机配置`,
    );
  }
  const config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  for (const key of ["cloudBaseUrl", "edgeToken", "factoryId", "agentKey"]) {
    if (!String(config[key] || "").trim()) {
      throw new Error(`config.json 缺少 ${key}`);
    }
  }
  if (config.factoryId !== "huakang-a") {
    throw new Error("3D打印边缘代理当前只允许 factoryId=huakang-a");
  }
  const printers = Array.isArray(config.bambuPrinters)
    ? config.bambuPrinters
    : [];
  if (!printers.length) {
    throw new Error("config.json 至少需要一台 bambuPrinters");
  }
  const machineNumbers = new Set();
  for (const printer of printers) {
    for (const key of ["machineNo", "host", "serial", "accessCode"]) {
      if (!String(printer[key] ?? "").trim()) {
        throw new Error(`打印机配置缺少 ${key}`);
      }
    }
    const machineNo = Number(printer.machineNo);
    if (!Number.isInteger(machineNo) || machineNo < 1 || machineNo > 100) {
      throw new Error(`无效的 machineNo: ${printer.machineNo}`);
    }
    if (machineNumbers.has(machineNo)) {
      throw new Error(`machineNo 重复: ${machineNo}`);
    }
    machineNumbers.add(machineNo);
  }
  return {
    ...config,
    cloudBaseUrl: String(config.cloudBaseUrl).replace(/\/+$/, ""),
    agentName: String(config.agentName || "华康A 3D边缘代理"),
    statusIntervalMs: Math.max(2000, Number(config.statusIntervalMs) || 5000),
    heartbeatIntervalMs: Math.max(
      10000,
      Number(config.heartbeatIntervalMs) || 30000,
    ),
    commandPollIntervalMs: Math.max(
      1000,
      Number(config.commandPollIntervalMs) || 3000,
    ),
    bambuPrinters: printers,
  };
}

const config = loadConfig();

function encodeMqttRemainingLength(length) {
  const bytes = [];
  do {
    let value = length % 128;
    length = Math.floor(length / 128);
    if (length > 0) value |= 128;
    bytes.push(value);
  } while (length > 0);
  return Buffer.from(bytes);
}

function mqttString(value) {
  const content = Buffer.from(String(value), "utf8");
  return Buffer.concat([
    Buffer.from([content.length >> 8, content.length & 0xff]),
    content,
  ]);
}

function buildMqttConnect(clientId, username, password) {
  const variableHeader = Buffer.concat([
    Buffer.from([0x00, 0x04, 0x4d, 0x51, 0x54, 0x54]),
    Buffer.from([0x04, 0xc2, 0x00, 0x3c]),
  ]);
  const payload = Buffer.concat([
    mqttString(clientId),
    mqttString(username),
    mqttString(password),
  ]);
  const remaining = variableHeader.length + payload.length;
  return Buffer.concat([
    Buffer.from([0x10]),
    encodeMqttRemainingLength(remaining),
    variableHeader,
    payload,
  ]);
}

function buildMqttSubscribe(packetId, topic) {
  const payload = Buffer.concat([
    Buffer.from([packetId >> 8, packetId & 0xff]),
    mqttString(topic),
    Buffer.from([0x00]),
  ]);
  return Buffer.concat([
    Buffer.from([0x82]),
    encodeMqttRemainingLength(payload.length),
    payload,
  ]);
}

function buildMqttPublish(topic, message) {
  const payload = Buffer.concat([
    mqttString(topic),
    Buffer.from(message, "utf8"),
  ]);
  return Buffer.concat([
    Buffer.from([0x30]),
    encodeMqttRemainingLength(payload.length),
    payload,
  ]);
}

function parseMqttPackets(buffer) {
  const packets = [];
  let offset = 0;
  while (offset < buffer.length) {
    const firstByte = buffer[offset];
    const type = firstByte & 0xf0;
    let multiplier = 1;
    let length = 0;
    let cursor = offset + 1;
    let bytes = 0;
    if (cursor >= buffer.length) break;
    let malformed = false;
    do {
      if (cursor >= buffer.length) return packets;
      if (bytes++ >= 4) {
        malformed = true;
        break;
      }
      const value = buffer[cursor++];
      length += (value & 127) * multiplier;
      multiplier *= 128;
    } while (buffer[cursor - 1] & 128);
    if (malformed) {
      offset += 1;
      continue;
    }
    if (cursor + length > buffer.length) break;
    packets.push({
      type,
      firstByte,
      data: buffer.slice(cursor, cursor + length),
      end: cursor + length,
    });
    offset = cursor + length;
  }
  return packets;
}

function cleanText(value) {
  return String(value || "").replace(
    /[\uFFFD\uD800-\uDFFF\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g,
    "",
  );
}

function normalizeState(value) {
  const state = String(value || "UNKNOWN").toUpperCase();
  const aliases = {
    PRINTING: "RUNNING",
    PREPARE: "RUNNING",
    PREPARING: "RUNNING",
    PAUSED: "PAUSE",
    COMPLETE: "FINISH",
    COMPLETED: "FINISH",
    FAILED: "FAILED",
    ERROR: "ERROR",
    IDLE: "IDLE",
    READY: "IDLE",
    FINISH: "FINISH",
    RUNNING: "RUNNING",
    PAUSE: "PAUSE",
  };
  return aliases[state] || state.slice(0, 32);
}

class BambuAdapter {
  constructor(printer) {
    this.printer = {
      ...printer,
      machineNo: Number(printer.machineNo),
      name: String(printer.name || `${printer.machineNo}号机`),
      model: String(printer.model || ""),
    };
    this.socket = null;
    this.buffer = Buffer.alloc(0);
    this.connected = false;
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.stopped = false;
    this.status = {
      machine_no: this.printer.machineNo,
      name: this.printer.name,
      printer_type: "bambu",
      model: this.printer.model,
      connected: false,
      state: "OFFLINE",
      current_file: "",
      progress_percent: 0,
      remaining_minutes: 0,
      live_material: "",
      nozzle_temperature: 0,
      bed_temperature: 0,
      error_text: "",
      observed_at: "",
      raw: {},
    };
  }

  start() {
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.reconnectTimer);
    clearInterval(this.pingTimer);
    this.socket?.destroy();
  }

  connect() {
    if (this.stopped || shuttingDown) return;
    clearTimeout(this.reconnectTimer);
    clearInterval(this.pingTimer);
    this.socket?.destroy();
    this.buffer = Buffer.alloc(0);
    this.connected = false;
    this.status.connected = false;
    this.status.state = "OFFLINE";
    const socket = tls.connect({
      host: this.printer.host,
      port: Number(this.printer.port) || 8883,
      rejectUnauthorized: this.printer.rejectUnauthorized === true,
      timeout: 10000,
    });
    this.socket = socket;
    socket.on("secureConnect", () => {
      const clientId = `rrnexus_${this.printer.machineNo}_${Date.now()}`;
      socket.write(
        buildMqttConnect(clientId, "bblp", this.printer.accessCode),
      );
    });
    socket.on("data", (chunk) => this.onData(chunk));
    socket.on("error", (error) => {
      this.connected = false;
      this.status.connected = false;
      this.status.state = "OFFLINE";
      this.status.error_text = cleanText(error.code || error.message).slice(
        0,
        4000,
      );
    });
    socket.on("close", () => {
      this.connected = false;
      this.status.connected = false;
      this.status.state = "OFFLINE";
      clearInterval(this.pingTimer);
      if (!this.stopped && !shuttingDown) {
        this.reconnectTimer = setTimeout(() => this.connect(), 10000);
      }
    });
    socket.on("timeout", () => socket.destroy());
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    if (this.buffer.length > MAX_MQTT_BUFFER_BYTES) {
      this.buffer = Buffer.alloc(0);
      this.socket?.destroy();
      return;
    }
    const packets = parseMqttPackets(this.buffer);
    if (packets.length) {
      this.buffer = this.buffer.slice(packets[packets.length - 1].end);
    }
    for (const packet of packets) {
      if (packet.type === 0x20) {
        this.onConnack(packet);
      } else if (packet.type === 0x30) {
        this.onPublish(packet);
      }
    }
  }

  onConnack(packet) {
    const returnCode = packet.data[1];
    if (returnCode !== 0) {
      this.status.error_text = `MQTT认证失败(rc=${returnCode})`;
      this.socket?.destroy();
      return;
    }
    this.connected = true;
    this.status.connected = true;
    this.status.error_text = "";
    console.log(`[${this.printer.name}] 局域网 MQTT 已连接`);
    this.socket.write(
      buildMqttSubscribe(1, `device/${this.printer.serial}/report`),
    );
    setTimeout(() => this.requestFullStatus(), 500);
    this.pingTimer = setInterval(() => {
      if (!this.connected || !this.socket) return;
      this.socket.write(Buffer.from([0xc0, 0x00]));
      this.requestFullStatus();
    }, 30000);
  }

  onPublish(packet) {
    try {
      const topicLength = (packet.data[0] << 8) | packet.data[1];
      const qos = (packet.firstByte >> 1) & 0x03;
      const payloadOffset = 2 + topicLength + (qos > 0 ? 2 : 0);
      const message = JSON.parse(
        packet.data.slice(payloadOffset).toString("utf8"),
      );
      if (!message.print) return;
      const report = message.print;
      if (report.gcode_state !== undefined) {
        this.status.state = normalizeState(report.gcode_state);
      }
      if (report.subtask_name !== undefined) {
        this.status.current_file = cleanText(report.subtask_name).slice(0, 512);
      } else if (report.gcode_file !== undefined) {
        this.status.current_file = cleanText(report.gcode_file).slice(0, 512);
      }
      if (report.mc_percent !== undefined) {
        this.status.progress_percent = Math.max(
          0,
          Math.min(100, Number(report.mc_percent) || 0),
        );
      }
      if (report.mc_remaining_time !== undefined) {
        this.status.remaining_minutes = Math.max(
          0,
          Number(report.mc_remaining_time) || 0,
        );
      }
      if (report.nozzle_temper !== undefined) {
        this.status.nozzle_temperature =
          Number(report.nozzle_temper) || 0;
      }
      if (report.bed_temper !== undefined) {
        this.status.bed_temperature = Number(report.bed_temper) || 0;
      }
      this.status.live_material = this.extractMaterial(report);
      this.status.connected = true;
      this.status.observed_at = new Date().toISOString();
      this.status.raw = {
        layerNum: Number(report.layer_num) || 0,
        totalLayers: Number(report.total_layer_num) || 0,
        printError: Number(report.print_error) || 0,
      };
    } catch (error) {
      this.status.error_text = `状态解析失败: ${cleanText(error.message)}`.slice(
        0,
        4000,
      );
    }
  }

  extractMaterial(report) {
    const ams = report.ams;
    if (!ams) return this.status.live_material;
    const current = ams.tray_now;
    if ((current === 255 || current === "255") && report.vt_tray) {
      return cleanText(report.vt_tray.tray_type).slice(0, 255);
    }
    const index = Number.parseInt(current, 10);
    if (!Number.isFinite(index) || !Array.isArray(ams.ams)) {
      return this.status.live_material;
    }
    const unit = ams.ams.find(
      (candidate) => Number.parseInt(candidate.id, 10) === Math.floor(index / 4),
    );
    const tray = unit?.tray?.find(
      (candidate) => Number.parseInt(candidate.id, 10) === index % 4,
    );
    return cleanText(tray?.tray_type || this.status.live_material).slice(0, 255);
  }

  requestFullStatus() {
    if (!this.connected || !this.socket) return;
    this.publish({
      pushing: {
        sequence_id: String(Date.now()),
        command: "pushall",
      },
    });
  }

  publish(payload) {
    if (!this.connected || !this.socket) {
      throw new Error("打印机局域网连接不可用");
    }
    this.socket.write(
      buildMqttPublish(
        `device/${this.printer.serial}/request`,
        JSON.stringify(payload),
      ),
    );
  }

  async execute(action) {
    if (!["pause", "resume"].includes(action)) {
      throw new Error(`不支持的控制指令: ${action}`);
    }
    if (!this.connected) {
      throw new Error("打印机离线，指令未发送");
    }
    if (action === "pause" && this.status.state !== "RUNNING") {
      throw new Error(`打印机当前为 ${this.status.state}，不可暂停`);
    }
    if (action === "resume" && this.status.state !== "PAUSE") {
      throw new Error(`打印机当前为 ${this.status.state}，不可恢复`);
    }
    this.publish({
      print: {
        sequence_id: String(Date.now()),
        command: action,
      },
    });
    return `${this.printer.name} 已接收 ${action} 指令`;
  }

  snapshot() {
    return {
      ...this.status,
      connected: this.connected && this.status.connected,
      state:
        this.connected && this.status.connected
          ? this.status.state
          : "OFFLINE",
      observed_at: new Date().toISOString(),
    };
  }
}

function hostFingerprint() {
  const identities = [];
  for (const [name, entries] of Object.entries(os.networkInterfaces())) {
    for (const entry of entries || []) {
      if (!entry.internal && entry.mac && entry.mac !== "00:00:00:00:00:00") {
        identities.push(`${name}:${entry.mac}`);
      }
    }
  }
  return crypto
    .createHash("sha256")
    .update(`${os.hostname()}|${identities.sort().join("|")}`)
    .digest("hex");
}

async function cloudRequest(endpoint, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${config.cloudBaseUrl}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Edge-Token": config.edgeToken,
        "User-Agent": `Royal-Regent-3D-Edge/${VERSION}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { detail: text.slice(0, 1000) };
      }
    }
    if (!response.ok) {
      throw new Error(
        `云端 HTTP ${response.status}: ${payload.detail || "请求失败"}`,
      );
    }
    lastCloudError = "";
    return payload;
  } catch (error) {
    const message =
      error.name === "AbortError" ? "云端请求超时" : cleanText(error.message);
    if (message !== lastCloudError) {
      console.error(`[云端] ${message}`);
      lastCloudError = message;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function heartbeat() {
  await cloudRequest("/api/three-d-printing/edge/heartbeat", {
    factory_id: config.factoryId,
    agent_key: config.agentKey,
    name: config.agentName,
    version: VERSION,
    host_fingerprint: hostFingerprint(),
    capabilities: ["status", "pause", "resume"],
  });
}

async function postStatuses() {
  await cloudRequest("/api/three-d-printing/edge/status", {
    factory_id: config.factoryId,
    agent_key: config.agentKey,
    statuses: [...adapters.values()].map((adapter) => adapter.snapshot()),
  });
}

async function acknowledge(command, status, message) {
  await cloudRequest(
    `/api/three-d-printing/edge/commands/${encodeURIComponent(command.id)}/ack`,
    {
      factory_id: config.factoryId,
      agent_key: config.agentKey,
      status,
      message: cleanText(message).slice(0, 4000),
    },
  );
}

async function pollCommands() {
  const payload = await cloudRequest(
    "/api/three-d-printing/edge/commands/claim",
    {
      factory_id: config.factoryId,
      agent_key: config.agentKey,
      limit: 10,
    },
  );
  for (const command of payload.commands || []) {
    const adapter = adapters.get(Number(command.machine_no));
    if (!adapter) {
      await acknowledge(command, "failed", "本机没有该机号的打印机配置");
      continue;
    }
    try {
      const result = await adapter.execute(command.action);
      await acknowledge(command, "succeeded", result);
      console.log(
        `[${adapter.printer.name}] 管理员指令 ${command.action} 执行成功`,
      );
    } catch (error) {
      const message = cleanText(error.message);
      await acknowledge(command, "failed", message);
      console.error(
        `[${adapter.printer.name}] 管理员指令 ${command.action} 失败: ${message}`,
      );
    }
  }
}

function repeat(task, intervalMs) {
  let running = false;
  const invoke = async () => {
    if (running || shuttingDown) return;
    running = true;
    try {
      await task();
    } catch {
      // cloudRequest already emits a rate-limited error.
    } finally {
      running = false;
    }
  };
  invoke();
  return setInterval(invoke, intervalMs);
}

async function start() {
  for (const printer of config.bambuPrinters) {
    const adapter = new BambuAdapter(printer);
    adapters.set(Number(printer.machineNo), adapter);
    adapter.start();
  }
  await heartbeat().catch(() => {});
  const timers = [
    repeat(heartbeat, config.heartbeatIntervalMs),
    repeat(postStatuses, config.statusIntervalMs),
    repeat(pollCommands, config.commandPollIntervalMs),
  ];
  const shutdown = () => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log("正在停止3D打印边缘代理...");
    timers.forEach(clearInterval);
    adapters.forEach((adapter) => adapter.stop());
    setTimeout(() => process.exit(0), 200);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
  console.log(
    `3D打印边缘代理 ${VERSION} 已启动，共 ${adapters.size} 台打印机；云端仅接收出站 HTTPS`,
  );
}

start().catch((error) => {
  console.error(`启动失败: ${cleanText(error.message)}`);
  process.exitCode = 1;
});
