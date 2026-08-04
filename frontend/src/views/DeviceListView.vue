<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { api, type DeviceItem, type FaultItem } from "../api";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAuthStore();

const activeTab = ref<"devices" | "faults">("devices");
const errorText = ref("");
const notice = ref("");

const statusOptions = [
  { value: "ONLINE", label: "在线" },
  { value: "OFFLINE", label: "离线" },
  { value: "FAULT", label: "故障" },
  { value: "DISABLED", label: "停用" },
];
const typeOptions = [
  { value: "CAMERA", label: "摄像头" },
  { value: "NVR", label: "录像机" },
  { value: "EDGE", label: "边缘分析盒" },
];
const faultStatusOptions = [
  { value: "PENDING", label: "待处理" },
  { value: "ASSIGNED", label: "已派单" },
  { value: "REPAIRED", label: "已修复" },
  { value: "AUTO_RECOVERED", label: "自动恢复" },
  { value: "CLOSED", label: "已关闭" },
];

const devStatus = ref("");
const devType = ref("");
const devKeyword = ref("");
const devPage = ref(1);
const devSize = 10;
const devTotal = ref(0);
const devices = ref<DeviceItem[]>([]);
const devLoading = ref(false);
const showBehaviors = ref(false);
const currentDevice = ref<DeviceItem | null>(null);
const deviceBehaviors = ref<any[]>([]);
const behaviorsLoading = ref(false);

const faultStatus = ref("");
const faultPage = ref(1);
const faultSize = 10;
const faultTotal = ref(0);
const faults = ref<FaultItem[]>([]);
const faultLoading = ref(false);

const showEditor = ref(false);
const editingId = ref<number | null>(null);
const submitting = ref(false);
const form = reactive({
  device_code: "",
  device_name: "",
  device_type: "CAMERA",
  location_text: "",
  region_code: "",
  region_name: "",
  status: "ONLINE",
  ip_address: "",
  port: undefined as number | undefined,
  manufacturer: "",
  model: "",
  remark: "",
});

function statusLabel(value: string): string {
  return statusOptions.find((item) => item.value === value)?.label || value;
}

function statusClass(value: string): string {
  return value === "ONLINE" ? "success" : value === "FAULT" ? "danger" : value === "OFFLINE" ? "warn" : "";
}

function typeLabel(value: string): string {
  return typeOptions.find((item) => item.value === value)?.label || value;
}

function faultStatusLabel(value: string): string {
  return faultStatusOptions.find((item) => item.value === value)?.label || value;
}

async function loadDevices() {
  devLoading.value = true;
  try {
    const result = await api.devices({ status: devStatus.value || undefined, device_type: devType.value || undefined, keyword: devKeyword.value || undefined, page: devPage.value, size: devSize });
    devices.value = result.list;
    devTotal.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    devLoading.value = false;
  }
}

async function loadFaults() {
  faultLoading.value = true;
  try {
    const result = await api.faults({ disposal_status: faultStatus.value || undefined, page: faultPage.value, size: faultSize });
    faults.value = result.list;
    faultTotal.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    faultLoading.value = false;
  }
}

function searchDevices() {
  devPage.value = 1;
  loadDevices();
}

async function viewBehaviors(item: DeviceItem) {
  currentDevice.value = item;
  showBehaviors.value = true;
  behaviorsLoading.value = true;
  deviceBehaviors.value = [];
  try {
    const result = await api.behaviors({ camera_id: item.id, page: 1, size: 10 });
    deviceBehaviors.value = result.list;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    behaviorsLoading.value = false;
  }
}

function searchFaults() {
  faultPage.value = 1;
  loadFaults();
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, { device_code: "", device_name: "", device_type: "CAMERA", location_text: "", region_code: "", region_name: "", status: "ONLINE", ip_address: "", port: undefined, manufacturer: "", model: "", remark: "" });
  showEditor.value = true;
}

function openEdit(item: DeviceItem) {
  editingId.value = item.id;
  Object.assign(form, {
    device_code: item.device_code,
    device_name: item.device_name,
    device_type: item.device_type,
    location_text: item.location_text || "",
    region_code: item.region_code || "",
    region_name: item.region_name || "",
    status: item.status,
    ip_address: item.ip_address || "",
    port: item.port ?? undefined,
    manufacturer: item.manufacturer || "",
    model: item.model || "",
    remark: item.remark || "",
  });
  showEditor.value = true;
}

async function submitForm() {
  if (!form.device_name.trim()) {
    errorText.value = "请填写设备名称";
    return;
  }
  submitting.value = true;
  try {
    if (editingId.value === null) {
      await api.createDevice({ ...form, device_code: form.device_code.trim(), device_name: form.device_name.trim() });
      notice.value = `设备 ${form.device_code} 已新增`;
    } else {
      await api.updateDevice(editingId.value, {
        device_name: form.device_name,
        location_text: form.location_text,
        region_code: form.region_code,
        region_name: form.region_name,
        status: form.status,
        ip_address: form.ip_address,
        port: form.port,
        manufacturer: form.manufacturer,
        model: form.model,
        remark: form.remark,
      });
      notice.value = `设备 ${form.device_code} 已更新`;
    }
    showEditor.value = false;
    await loadDevices();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

async function closeFault(item: FaultItem) {
  submitting.value = true;
  try {
    await api.closeFault(item.id);
    item.disposal_status = "CLOSED";
    notice.value = `故障 #${item.id} 已关闭`;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}



onMounted(() => {
  if (route.query.tab === "faults" && auth.hasPermission("device:info:view")) {
    activeTab.value = "faults";
  }
  loadDevices();
  loadFaults();
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>设备列表管理</h2><p>摄像头 / 录像机 / 边缘盒台账与故障记录</p></div>
      <div class="tabs">
        <button :class="{ selected: activeTab === 'devices' }" @click="activeTab = 'devices'">设备台账</button>
        <button v-if="auth.hasPermission('device:info:view')" :class="{ selected: activeTab === 'faults' }" @click="activeTab = 'faults'">故障记录</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <div v-if="activeTab === 'devices'" class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="devKeyword" placeholder="搜索设备名称 / 编号 / 安装位置" @keyup.enter="searchDevices" /></div>
        <select v-model="devStatus" @change="searchDevices">
          <option value="">全部状态</option>
          <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <select v-model="devType" @change="searchDevices">
          <option value="">全部类型</option>
          <option v-for="item in typeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <button class="primary" @click="searchDevices">查询</button>
        <button v-if="auth.hasPermission('device:create')" class="btn-sm btn-confirm" @click="openCreate">+ 新增设备</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>设备编号</span><span>名称 / 位置</span><span>类型</span><span>状态</span><span>健康分</span><span>最近心跳</span><span>IP</span><span>操作</span></div>
        <div v-if="devLoading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!devices.length" class="table-row"><span>暂无符合条件的设备</span></div>
        <div v-for="item in devices" :key="item.id" class="table-row">
          <span><b>{{ item.device_code }}</b></span>
          <span>{{ item.device_name }}<br /><small>{{ item.region_name || "—" }} · {{ item.location_text || "—" }}</small></span>
          <span>{{ typeLabel(item.device_type) }}</span>
          <span :class="statusClass(item.status)">● {{ statusLabel(item.status) }}</span>
          <span>{{ item.health_score ?? "—" }}</span>
          <span><small>{{ item.last_heartbeat_time || "—" }}</small></span>
          <span><small>{{ item.ip_address || "—" }}</small></span>
          <span>
            <button v-if="auth.hasPermission('device:update')" class="btn-sm btn-assign" @click="openEdit(item)">编辑</button>
            <button v-if="auth.hasPermission('device:info:view')" class="btn-sm" @click="viewBehaviors(item)">行为</button>
          </span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ devTotal }} 条</span>
        <button :disabled="devPage <= 1" @click="devPage--; loadDevices()">上一页</button>
        <span>第 {{ devPage }} 页</span>
        <button :disabled="devPage * devSize >= devTotal" @click="devPage++; loadDevices()">下一页</button>
      </div>
    </div>

    <div v-else class="panel data-panel">
      <div class="toolbar">
        <select v-model="faultStatus" @change="searchFaults">
          <option value="">全部处置状态</option>
          <option v-for="item in faultStatusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <button class="primary" @click="searchFaults">查询</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>发生时间</span><span>设备</span><span>故障类型</span><span>级别</span><span>描述</span><span>处置状态</span><span>操作</span></div>
        <div v-if="faultLoading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!faults.length" class="table-row"><span>暂无故障记录</span></div>
        <div v-for="item in faults" :key="item.id" class="table-row">
          <span><small>{{ item.occurrence_time }}</small></span>
          <span><b>{{ item.device_name }}</b><br /><small>{{ item.device_code }}</small></span>
          <span>{{ item.fault_type }}</span>
          <span :class="item.fault_level === 'CRITICAL' || item.fault_level === 'HIGH' ? 'danger' : item.fault_level === 'MEDIUM' ? 'warn' : ''">{{ item.fault_level }}</span>
          <span><small>{{ item.fault_desc }}</small><br /><small v-if="item.repair_remark">处置：{{ item.repair_remark }}</small></span>
          <span>{{ faultStatusLabel(item.disposal_status) }}</span>
          <span><button v-if="item.disposal_status !== 'CLOSED' && auth.hasPermission('device:update')" class="btn-sm btn-ignore" :disabled="submitting" @click="closeFault(item)">关闭故障</button><span v-else>—</span></span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ faultTotal }} 条</span>
        <button :disabled="faultPage <= 1" @click="faultPage--; loadFaults()">上一页</button>
        <span>第 {{ faultPage }} 页</span>
        <button :disabled="faultPage * faultSize >= faultTotal" @click="faultPage++; loadFaults()">下一页</button>
      </div>
    </div>

    <div v-if="showBehaviors" class="modal-mask" @click.self="showBehaviors = false">
      <div class="modal" style="max-width: 720px; width: 90%">
        <button class="close" @click="showBehaviors = false">×</button>
        <h2>设备行为记录 - {{ currentDevice?.device_name }}</h2>
        <div v-if="behaviorsLoading" style="padding: 20px; text-align: center">加载中...</div>
        <div v-else-if="!deviceBehaviors.length" style="padding: 20px; text-align: center">暂无行为记录</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>级别</th>
              <th>状态</th>
              <th>描述</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in deviceBehaviors" :key="b.behavior_id">
              <td>{{ b.detected_at }}</td>
              <td>{{ b.type_name }}</td>
              <td>{{ b.level_name }}</td>
              <td>{{ b.status_name }}</td>
              <td><small>{{ b.description }}</small></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showEditor" class="modal-mask" @click.self="showEditor = false">
      <div class="modal">
        <button class="close" @click="showEditor = false">×</button>
        <h2>{{ editingId === null ? "新增设备" : "编辑设备 " + form.device_code }}</h2>
        <label>设备编号</label>
        <input v-model="form.device_code" :disabled="editingId !== null" placeholder="如 CAM-025" />
        <label>设备名称</label>
        <input v-model="form.device_name" placeholder="如 周界西段摄像头" />
        <label v-if="editingId === null">设备类型</label>
        <select v-if="editingId === null" v-model="form.device_type" class="role-select">
          <option v-for="item in typeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <label v-else>设备状态</label>
        <select v-if="editingId !== null" v-model="form.status" class="role-select">
          <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <label>安装位置</label>
        <input v-model="form.location_text" placeholder="如 园区西侧围墙" />
        <label>所属区域</label>
        <input v-model="form.region_name" placeholder="如 周界" />
        <label>IP 地址</label>
        <input v-model="form.ip_address" placeholder="如 192.168.10.91" />
        <label>厂商</label>
        <input v-model="form.manufacturer" placeholder="如 海康威视" />
        <label>型号</label>
        <input v-model="form.model" />
        <label>备注</label>
        <input v-model="form.remark" />
        <button class="primary" :disabled="submitting" @click="submitForm">{{ editingId === null ? "确认新增" : "保存修改" }}</button>
      </div>
    </div>
  </div>
</template>
