<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type BackupItem, type RestoreLogItem } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();

type TabKey = "backup" | "restore" | "log";
const activeTab = ref<TabKey>("backup");

const backupType = ref<"MANUAL" | "AUTO">("MANUAL");
const backupPeriod = ref<"DAILY" | "WEEKLY" | "MONTHLY" | "YEARLY">("DAILY");
const backupTime = ref("03:00");
const backupDayOfWeek = ref<number>(1); // 周一=1 ... 周日=0 或 7（前端用 1-7）
const backupDayOfMonth = ref<number>(1);
const backupMonth = ref<number>(1); // 1-12
const strategyDesc = ref("");

const backups = ref<BackupItem[]>([]);
const restoreLogs = ref<RestoreLogItem[]>([]);
const loading = ref(false);
const creating = ref(false);
const restoring = ref(false);
const errorText = ref("");
const notice = ref("");

const lastBackup = ref<BackupItem | null>(null);
const lastVerify = ref<{ ok: boolean; name: string; msg: string } | null>(null);
const pendingRestore = ref<BackupItem | null>(null);
const pendingDelete = ref<BackupItem | null>(null);

// —— 前端分页（每页 10 条）——
const pageSize = 10;
const backupPage = ref(1);
const restorePage = ref(1);
const backupLogPage = ref(1);
const restoreLogPage = ref(1);
const jumpBackup = ref<number | null>(null);
const jumpRestore = ref<number | null>(null);
const jumpBackupLog = ref<number | null>(null);
const jumpRestoreLog = ref<number | null>(null);

const pagedBackups = computed(() => backups.value.slice((backupPage.value - 1) * pageSize, backupPage.value * pageSize));
const pagedRestoreBackups = computed(() => backups.value.slice((restorePage.value - 1) * pageSize, restorePage.value * pageSize));
const pagedBackupLogs = computed(() => backups.value.slice((backupLogPage.value - 1) * pageSize, backupLogPage.value * pageSize));
const pagedRestoreLogs = computed(() => restoreLogs.value.slice((restoreLogPage.value - 1) * pageSize, restoreLogPage.value * pageSize));

function goPage(target: { value: number }, jump: { value: number | null }, listTotal: number) {
  const maxPage = Math.max(1, Math.ceil(listTotal / pageSize));
  let p = Number(jump.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  target.value = p;
  jump.value = null;
}

const backupTotal = computed(() => backups.value.length);

const STATUS_LABEL: Record<string, string> = { SUCCESS: "成功", FAILED: "失败", RESTORED: "已恢复" };
const TYPE_LABEL: Record<string, string> = { MANUAL: "手动", AUTO: "自动" };

function statusLabel(s: string) { return STATUS_LABEL[s] || s; }
function typeLabel(t: string) { return TYPE_LABEL[t] || t; }
function statusClass(s: string) {
  return { SUCCESS: "ok", FAILED: "bad", RESTORED: "warn" }[s] || "";
}
function sizeLabel(bytes: number) {
  if (!bytes) return "—";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

async function loadBackups() {
  loading.value = true;
  try {
    const result = await api.backups({ page: 1, size: 100 });
    backups.value = result.list;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function loadRestoreLogs() {
  try {
    const result = await api.restoreLogs({ page: 1, size: 50 });
    restoreLogs.value = result.list;
  } catch (error: any) {
    errorText.value = error.message;
  }
}

async function createBackup() {
  creating.value = true;
  errorText.value = "";
  try {
    // 仅在自动类型时构造周期描述；手动类型只保留用户备注
    let composed = "";
    if (backupType.value === "AUTO") {
      const periodLabel = { DAILY: "每日", WEEKLY: "每周", MONTHLY: "每月", YEARLY: "每年" }[backupPeriod.value];
      const dowLabel = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][backupDayOfWeek.value];
      const time = backupTime.value || "03:00";
      if (backupPeriod.value === "DAILY") composed = `每日 ${time}`;
      else if (backupPeriod.value === "WEEKLY") composed = `每周 ${dowLabel} ${time}`;
      else if (backupPeriod.value === "MONTHLY") composed = `每月 ${backupDayOfMonth.value}日 ${time}`;
      else if (backupPeriod.value === "YEARLY") composed = `每年 ${backupMonth.value}月${backupDayOfMonth.value}日 ${time}`;
      if (strategyDesc.value.trim()) composed += ` - ${strategyDesc.value.trim()}`;
    } else {
      composed = strategyDesc.value.trim() || "手动备份";
    }
    const result = await api.createBackup({
      backup_type: backupType.value,
      strategy_desc: composed,
    });
    lastBackup.value = result;
    notice.value = `备份创建成功（${result.backup_name}），文件已落盘 ${sizeLabel(result.file_size)}`;
    strategyDesc.value = "";
    await loadBackups();
  } catch (error: any) {
    errorText.value = error.message || "备份失败";
  } finally {
    creating.value = false;
  }
}

async function restoreBackup(item: BackupItem) {
  errorText.value = "";
  restoring.value = true;
  try {
    await api.restoreBackup(item.backup_id);
    lastVerify.value = { ok: true, name: item.backup_name, msg: "恢复完成，已执行并通过完整性校验（mysql 退出码 0）" };
    notice.value = "数据恢复成功";
    await loadBackups();
    await loadRestoreLogs();
  } catch (error: any) {
    lastVerify.value = { ok: false, name: item.backup_name, msg: error.message || "恢复失败" };
    errorText.value = error.message || "恢复失败";
    await loadRestoreLogs();
  } finally {
    restoring.value = false;
  }
}

async function deleteBackup(item: BackupItem) {
  errorText.value = "";
  try {
    await api.deleteBackup(item.backup_id);
    notice.value = "备份已删除";
    await loadBackups();
  } catch (error: any) {
    errorText.value = error.message;
  }
}

onMounted(() => {
  loadBackups();
  loadRestoreLogs();
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div>
        <h2>数据备份与恢复</h2>
        <p>备份策略配置、历史快照选择、一键恢复（含二次确认与结果校验）</p>
        <div class="heading-tabs">
          <button :class="['tab-btn', activeTab === 'backup' ? 'active' : '']" @click="activeTab = 'backup'">数据备份</button>
          <button :class="['tab-btn', activeTab === 'restore' ? 'active' : '']" @click="activeTab = 'restore'">数据恢复</button>
          <button :class="['tab-btn', activeTab === 'log' ? 'active' : '']" @click="activeTab = 'log'">备份日志</button>
        </div>
      </div>
      <div class="tabs">
        <button class="primary" :disabled="creating" @click="createBackup">{{ creating ? "执行中..." : "立即备份" }}</button>
        <button :disabled="loading" @click="loadBackups">刷新</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <!-- ============ 数据备份 Tab ============ -->
    <div v-show="activeTab === 'backup'">
      <div class="panel data-panel" style="margin-bottom: 12px">
        <div class="toolbar"><span style="font-weight: 600">备份策略配置</span></div>
        <div class="backup-form">
          <div class="form-row">
            <span class="form-label">备份类型</span>
            <div class="radio-group">
              <label class="radio"><input type="radio" v-model="backupType" value="MANUAL" /> 手动（立即执行）</label>
              <label class="radio"><input type="radio" v-model="backupType" value="AUTO" /> 自动（按周期）</label>
            </div>
          </div>

          <!-- 自动备份才显示周期选择 -->
          <template v-if="backupType === 'AUTO'">
            <div class="form-row">
              <span class="form-label">备份周期</span>
              <div class="radio-group">
                <label class="radio"><input type="radio" v-model="backupPeriod" value="DAILY" /> 每日</label>
                <label class="radio"><input type="radio" v-model="backupPeriod" value="WEEKLY" /> 每周</label>
                <label class="radio"><input type="radio" v-model="backupPeriod" value="MONTHLY" /> 每月</label>
                <label class="radio"><input type="radio" v-model="backupPeriod" value="YEARLY" /> 每年</label>
              </div>
            </div>

            <!-- 每日：时间 -->
            <div v-if="backupPeriod === 'DAILY'" class="form-row">
              <span class="form-label">执行时刻</span>
              <input type="time" v-model="backupTime" />
            </div>

            <!-- 每周：周几 + 时间（同行 flex 横排） -->
            <div v-if="backupPeriod === 'WEEKLY'" class="form-row">
              <span class="form-label">每周</span>
              <select v-model.number="backupDayOfWeek">
                <option :value="1">周一</option><option :value="2">周二</option><option :value="3">周三</option>
                <option :value="4">周四</option><option :value="5">周五</option><option :value="6">周六</option><option :value="7">周日</option>
              </select>
              <span class="inline-label">时间</span>
              <input type="time" v-model="backupTime" />
            </div>

            <!-- 每月：几号 + 时间（同行 flex 横排） -->
            <div v-if="backupPeriod === 'MONTHLY'" class="form-row">
              <span class="form-label">每月</span>
              <select v-model.number="backupDayOfMonth">
                <option v-for="d in 31" :key="d" :value="d">{{ d }}日</option>
              </select>
              <span class="inline-label">时间</span>
              <input type="time" v-model="backupTime" />
            </div>

            <!-- 每年：几月 + 几号 + 时间（同行 flex 横排） -->
            <div v-if="backupPeriod === 'YEARLY'" class="form-row">
              <span class="form-label">每年</span>
              <select v-model.number="backupMonth">
                <option v-for="m in 12" :key="m" :value="m">{{ m }}月</option>
              </select>
              <select v-model.number="backupDayOfMonth">
                <option v-for="d in 31" :key="d" :value="d">{{ d }}日</option>
              </select>
              <span class="inline-label">时间</span>
              <input type="time" v-model="backupTime" />
            </div>
          </template>

          <div class="form-row">
            <span class="form-label">策略描述</span>
            <input v-model="strategyDesc" :placeholder="backupType === 'MANUAL' ? '例：发布前全量快照' : '例：重大变更前自动备份'" />
          </div>
          <div class="form-row form-hint">
            <span class="form-label"></span>
            <span class="muted">备份方式：mysqldump --single-transaction · 文件落盘至 backend/data_backups/ · 记录入 sys_data_backup</span>
          </div>
          <div class="form-row form-action">
            <span class="form-label"></span>
            <button class="primary" :disabled="creating" @click="createBackup">{{ creating ? "执行中..." : (backupType === 'MANUAL' ? '立即执行备份' : '保存策略配置') }}</button>
          </div>
        </div>
      </div>

      <div class="panel data-panel kv-panel" style="margin-bottom: 12px">
        <div class="toolbar"><span style="font-weight: 600">最近一次备份结果</span></div>
        <div v-if="lastBackup" class="kv-list">
          <div><span class="k">备份名称</span><span>{{ lastBackup.backup_name }}</span></div>
          <div><span class="k">类型 / 状态</span><span>{{ typeLabel(lastBackup.backup_type) }} / <em :class="statusClass(lastBackup.status)">{{ statusLabel(lastBackup.status) }}</em></span></div>
          <div><span class="k">文件大小</span><span>{{ sizeLabel(lastBackup.file_size) }}</span></div>
          <div><span class="k">策略描述</span><span>{{ lastBackup.strategy_desc || "—" }}</span></div>
          <div><span class="k">操作人 / 时间</span><span>{{ lastBackup.operator_name || "系统" }} · {{ lastBackup.create_time }}</span></div>
          <div><span class="k">文件路径</span><span><small>{{ lastBackup.file_path }}</small></span></div>
        </div>
        <div v-else class="muted" style="padding: 6px 4px">暂无最近备份，先在上方填写策略后点击"立即执行备份"试试。</div>
      </div>

      <div class="panel data-panel">
        <div class="toolbar"><span style="font-weight: 600">备份历史</span><span style="margin-left: auto">共 {{ backupTotal }} 个</span></div>
        <div class="table full">
          <div class="table-head"><span>名称</span><span>类型</span><span>大小</span><span>状态</span><span>操作人</span><span>创建时间</span><span>操作</span></div>
          <div v-if="loading" class="table-row"><span>加载中...</span></div>
          <div v-else-if="!backups.length" class="table-row"><span>暂无备份。先在"备份策略配置"填写策略后点击"立即备份"。</span></div>
          <div v-for="item in pagedBackups" :key="item.backup_id" class="table-row">
            <span>{{ item.backup_name }}<br /><small>{{ item.strategy_desc || "—" }}</small></span>
            <span>{{ typeLabel(item.backup_type) }}</span>
            <span>{{ sizeLabel(item.file_size) }}</span>
            <span :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span>
            <span>{{ item.operator_name || "系统" }}</span>
            <span><small>{{ item.create_time }}</small></span>
            <span class="row-actions">
              <button :disabled="restoring" class="primary" @click="pendingRestore = item">恢复</button>
              <button class="danger" @click="pendingDelete = item">删除</button>
            </span>
          </div>
        </div>
        <div class="pager">
          <span>共 {{ backupTotal }} 条</span>
          <button :disabled="backupPage <= 1" @click="backupPage--">上一页</button>
          <span>第 {{ backupPage }} 页 / 共 {{ Math.max(1, Math.ceil(backupTotal / pageSize)) }} 页</span>
          <button :disabled="backupPage * pageSize >= backupTotal" @click="backupPage++">下一页</button>
          <span>跳转到</span>
          <input v-model.number="jumpBackup" type="number" min="1" :max="Math.max(1, Math.ceil(backupTotal / pageSize))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goPage(backupPage, jumpBackup, backupTotal)" />
          <span>页</span>
          <button @click="goPage(backupPage, jumpBackup, backupTotal)" :disabled="!jumpBackup">GO</button>
        </div>
      </div>
    </div>

    <!-- ============ 数据恢复 Tab ============ -->
    <div v-show="activeTab === 'restore'">
      <div class="panel data-panel">
        <div class="toolbar">
          <span style="font-weight: 600">选择历史备份 · 二次确认 · 执行恢复 · 校验结果</span>
          <span style="margin-left: auto" class="muted">⚠ 恢复会覆盖当前数据库，仅超级管理员可操作</span>
        </div>
        <div class="table full">
          <div class="table-head">
            <span>备份名称</span><span>类型</span><span>大小</span><span>创建时间</span><span>操作</span>
          </div>
          <div v-if="loading" class="table-row"><span>加载中...</span></div>
          <div v-else-if="!backups.length" class="table-row"><span>暂无可用备份，请先切到"数据备份"页签创建快照</span></div>
          <div v-for="item in pagedRestoreBackups" :key="item.backup_id" class="table-row">
            <span>{{ item.backup_name }}<br /><small>{{ item.strategy_desc || "—" }}</small></span>
            <span>{{ typeLabel(item.backup_type) }}<br /><small :class="statusClass(item.status)">{{ statusLabel(item.status) }}</small></span>
            <span>{{ sizeLabel(item.file_size) }}</span>
            <span><small>{{ item.create_time }}</small></span>
            <span class="row-actions">
              <button :disabled="restoring" class="primary" @click="pendingRestore = item">恢复</button>
              <button class="danger" @click="pendingDelete = item">删除</button>
            </span>
          </div>
        </div>
        <div class="pager">
          <span>共 {{ backupTotal }} 条</span>
          <button :disabled="restorePage <= 1" @click="restorePage--">上一页</button>
          <span>第 {{ restorePage }} 页 / 共 {{ Math.max(1, Math.ceil(backupTotal / pageSize)) }} 页</span>
          <button :disabled="restorePage * pageSize >= backupTotal" @click="restorePage++">下一页</button>
          <span>跳转到</span>
          <input v-model.number="jumpRestore" type="number" min="1" :max="Math.max(1, Math.ceil(backupTotal / pageSize))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goPage(restorePage, jumpRestore, backupTotal)" />
          <span>页</span>
          <button @click="goPage(restorePage, jumpRestore, backupTotal)" :disabled="!jumpRestore">GO</button>
        </div>
      </div>
    </div>

    <!-- ============ 备份日志 Tab ============ -->
    <div v-show="activeTab === 'log'">
      <div class="panel data-panel">
        <div class="toolbar"><span style="font-weight: 600">备份执行日志（操作审计）</span></div>
        <div class="table full">
          <div class="table-head"><span>时间</span><span>备份名称</span><span>类型</span><span>状态</span><span>大小</span><span>策略描述</span><span>操作人</span></div>
          <div v-if="!backups.length" class="table-row"><span>暂无备份日志</span></div>
          <div v-for="item in pagedBackupLogs" :key="`log-${item.backup_id}`" class="table-row">
            <span><small>{{ item.create_time }}</small></span>
            <span>{{ item.backup_name }}</span>
            <span>{{ typeLabel(item.backup_type) }}</span>
            <span :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span>
            <span>{{ sizeLabel(item.file_size) }}</span>
            <span><small>{{ item.strategy_desc || "—" }}</small></span>
            <span>{{ item.operator_name || "系统" }}</span>
          </div>
        </div>
        <div class="pager">
          <span>共 {{ backupTotal }} 条</span>
          <button :disabled="backupLogPage <= 1" @click="backupLogPage--">上一页</button>
          <span>第 {{ backupLogPage }} 页 / 共 {{ Math.max(1, Math.ceil(backupTotal / pageSize)) }} 页</span>
          <button :disabled="backupLogPage * pageSize >= backupTotal" @click="backupLogPage++">下一页</button>
          <span>跳转到</span>
          <input v-model.number="jumpBackupLog" type="number" min="1" :max="Math.max(1, Math.ceil(backupTotal / pageSize))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goPage(backupLogPage, jumpBackupLog, backupTotal)" />
          <span>页</span>
          <button @click="goPage(backupLogPage, jumpBackupLog, backupTotal)" :disabled="!jumpBackupLog">GO</button>
        </div>
      </div>

      <div class="panel data-panel" style="margin-top: 12px">
        <div class="toolbar"><span style="font-weight: 600">恢复执行日志</span></div>
        <div class="table full">
          <div class="table-head"><span>时间</span><span>来源备份</span><span>结果</span><span>操作人</span><span>说明</span></div>
          <div v-if="!restoreLogs.length" class="table-row"><span>暂无恢复日志</span></div>
          <div v-for="item in pagedRestoreLogs" :key="item.restore_id" class="table-row">
            <span><small>{{ item.restore_time }}</small></span>
            <span>{{ item.backup_name || `#${item.backup_id}` }}</span>
            <span :class="statusClass(item.restore_status)">{{ item.restore_status === "SUCCESS" ? "成功" : "失败" }}</span>
            <span>{{ item.operator_name || "系统" }}</span>
            <span><small>{{ item.result_msg || "—" }}</small></span>
          </div>
        </div>
        <div class="pager">
          <span>共 {{ restoreLogs.length }} 条</span>
          <button :disabled="restoreLogPage <= 1" @click="restoreLogPage--">上一页</button>
          <span>第 {{ restoreLogPage }} 页 / 共 {{ Math.max(1, Math.ceil(restoreLogs.length / pageSize)) }} 页</span>
          <button :disabled="restoreLogPage * pageSize >= restoreLogs.length" @click="restoreLogPage++">下一页</button>
          <span>跳转到</span>
          <input v-model.number="jumpRestoreLog" type="number" min="1" :max="Math.max(1, Math.ceil(restoreLogs.length / pageSize))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goPage(restoreLogPage, jumpRestoreLog, restoreLogs.length)" />
          <span>页</span>
          <button @click="goPage(restoreLogPage, jumpRestoreLog, restoreLogs.length)" :disabled="!jumpRestoreLog">GO</button>
        </div>
      </div>
    </div>

    <!-- ============ 恢复/删除 二次确认对话框 ============ -->
    <div v-if="pendingRestore" class="modal-mask" @click.self="pendingRestore = null">
      <div class="modal-card">
        <h3>确认恢复数据</h3>
        <p class="modal-desc">将从以下备份恢复（覆盖当前数据库，操作不可撤销）：</p>
        <div class="modal-kv">
          <div><span class="k">备份名称</span><span>{{ pendingRestore.backup_name }}</span></div>
          <div><span class="k">类型</span><span>{{ typeLabel(pendingRestore.backup_type) }}</span></div>
          <div><span class="k">文件大小</span><span>{{ sizeLabel(pendingRestore.file_size) }}</span></div>
          <div><span class="k">策略描述</span><span>{{ pendingRestore.strategy_desc || "—" }}</span></div>
          <div><span class="k">创建时间</span><span>{{ pendingRestore.create_time }}</span></div>
        </div>
        <div class="modal-actions">
          <button @click="pendingRestore = null">取消</button>
          <button class="primary" :disabled="restoring" @click="restoreBackup(pendingRestore!); pendingRestore = null">确认恢复</button>
        </div>
      </div>
    </div>
    <div v-if="pendingDelete" class="modal-mask" @click.self="pendingDelete = null">
      <div class="modal-card">
        <h3>确认删除备份</h3>
        <p class="modal-desc">删除后备份文件将一并移除，无法恢复。</p>
        <div class="modal-kv">
          <div><span class="k">备份名称</span><span>{{ pendingDelete.backup_name }}</span></div>
          <div><span class="k">文件大小</span><span>{{ sizeLabel(pendingDelete.file_size) }}</span></div>
          <div><span class="k">创建时间</span><span>{{ pendingDelete.create_time }}</span></div>
        </div>
        <div class="modal-actions">
          <button @click="pendingDelete = null">取消</button>
          <button class="danger" @click="deleteBackup(pendingDelete!); pendingDelete = null">确认删除</button>
        </div>
      </div>
    </div>

    <!-- ============ 最近一次恢复校验结果 ============ -->
    <div v-if="lastVerify" class="verify-card" :class="lastVerify.ok ? 'ok' : 'bad'">
      <button class="verify-close" @click="lastVerify = null" aria-label="关闭">×</button>
      <strong>{{ lastVerify.ok ? '✅ 恢复校验通过' : '❌ 恢复失败' }}</strong>
      <span>{{ lastVerify.name }}</span>
      <small>{{ lastVerify.msg }}</small>
    </div>
  </div>
</template>

<style scoped>
.tab-btn {
  padding: 6px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-tertiary);
  background: #fff;
  cursor: pointer;
}
.tab-btn.active {
  background: var(--color-info, #3788e8);
  color: #fff;
  border-color: var(--color-info, #3788e8);
}
.heading-tabs {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.heading-tabs .tab-btn {
  padding: 6px 18px;
}
.backup-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}
.backup-form .form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  justify-content: flex-start;
}
.backup-form .form-row .form-label {
  flex: 0 0 auto;
  min-width: 70px;
  color: var(--text-secondary);
  font-size: 13px;
}
.backup-form .form-row .inline-label {
  color: var(--text-secondary);
  font-size: 13px;
}
.backup-form .form-row input,
.backup-form .form-row select {
  width: auto;
  min-width: 120px;
  padding: 6px 10px;
  border: 1px solid var(--border-tertiary);
  border-radius: 4px;
  font-size: 13px;
}
.radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.radio {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  white-space: nowrap;
}
.kv-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 4px;
}
.kv-panel {
  padding-top: 10px !important;
  padding-bottom: 10px !important;
}
/* .pager 样式已迁到 app.css 全局，所有列表页统一 */
.kv-list > div {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 12px;
  font-size: 13px;
}
.kv-list .k {
  color: var(--text-secondary);
}
.row-actions {
  display: flex;
  gap: 6px;
}
button.danger {
  color: #a32d2d;
  border-color: #f0b4b4;
}
button.danger:hover {
  background: #fcebeb;
}
.muted {
  color: var(--text-secondary);
  font-size: 12px;
}
.ok { color: #1d9e75; }
.bad { color: #a32d2d; }
.warn { color: #ba7517; }

/* 二次确认对话框 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.modal-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  min-width: 380px;
  max-width: 520px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}
.modal-card h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
}
.modal-desc {
  margin: 0 0 12px 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.modal-kv {
  background: #f7f8fa;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 16px;
}
.modal-kv > div {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 8px;
  font-size: 13px;
  padding: 2px 0;
}
.modal-kv .k {
  color: var(--text-secondary);
}
.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.modal-actions button {
  padding: 7px 18px;
  border-radius: 4px;
  border: 1px solid var(--border-tertiary);
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}
.modal-actions button.primary {
  background: var(--color-info, #3788e8);
  color: #fff;
  border-color: var(--color-info, #3788e8);
}
.modal-actions button.danger {
  background: #a32d2d;
  color: #fff;
  border-color: #a32d2d;
}
.modal-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 恢复校验结果条 */
.verify-card {
  position: fixed;
  right: 24px;
  bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 38px 14px 18px;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  font-size: 13px;
  z-index: 998;
  min-width: 280px;
  max-width: 420px;
}
.verify-card.ok {
  background: #eaf7f1;
  border: 1px solid #1d9e75;
  color: #0f6e56;
}
.verify-card.bad {
  background: #fcebeb;
  border: 1px solid #a32d2d;
  color: #791f1f;
}
.verify-card small {
  color: var(--text-secondary);
  font-size: 12px;
}
.verify-close {
  position: absolute;
  top: 6px;
  right: 8px;
  background: transparent !important;
  border: 0;
  font-size: 18px;
  line-height: 1;
  color: inherit;
  opacity: 0.6;
  cursor: pointer;
  padding: 2px 6px;
}
.verify-close:hover {
  opacity: 1;
}
</style>