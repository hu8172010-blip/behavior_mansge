import { http } from "./http";
import { useSettingsStore } from "../stores/settings";

function getLabIncludeParam(): { include_lab: boolean } {
  try {
    const settings = useSettingsStore();
    // settings.filterLabData is true when we want to FILTER OUT lab data
    // The backend parameter include_lab is true when we want to INCLUDE lab data
    return { include_lab: !settings.filterLabData };
  } catch (e) {
    // Fallback if store is not initialized yet
    return { include_lab: false };
  }
}

export interface LoginResult {
  account_id: number;
  login_name: string;
  real_name: string;
  dept: string | null;
  type_id: number;
  role_name: string | null;
  permissions: string[];
  token: string;
}

export interface EnumOption {
  id: number;
  name: string;
}

export interface MetaEnums {
  severity_levels: EnumOption[];
  alert_statuses: EnumOption[];
  work_order_statuses: EnumOption[];
  behavior_types: EnumOption[];
  roles: { id: number; name: string; desc: string | null }[];
  handlers: { account_id: number; real_name: string }[];
}

export interface PageData<T> {
  list: T[];
  total: number;
  page: number;
  size: number;
}

export interface AlertItem {
  alert_id: number;
  behavior_id: number;
  alert_time: string;
  alert_status_id: number;
  status_name: string;
  is_marked_focus: number;
  type_name: string;
  level_name: string;
  description: string | null;
  confidence_score: number | null;
  track_id: number | null;
  device_name: string | null;
  device_code: string | null;
  region_name: string | null;
  is_lab?: number;
}

export interface WorkOrderItem {
  work_order_id: number;
  work_order_no: string;
  alert_id: number;
  behavior_id: number;
  work_order_status_id: number;
  status_name: string;
  type_name: string;
  level_name: string;
  description: string | null;
  assignee_name: string;
  assigned_to: number;
  assigned_at: string | null;
  handled_at: string | null;
  handle_result: string | null;
  handle_duration_minutes: number | null;
  is_lab?: number;
}

export interface WorkOrderDetail extends WorkOrderItem {
  detected_at: string | null;
  confidence_score: number | null;
  track_id: number | null;
  camera_name: string | null;
  camera_code: string | null;
  region_name: string | null;
  person_desc: string | null;
  assigner_name: string | null;
}

export interface BehaviorItem {
  behavior_id: number;
  detected_at: string;
  type_name: string;
  level_name: string;
  alert_status_id: number;
  status_name: string;
  description: string | null;
  confidence_score: number | null;
  person_id: number | null;
  track_id: number | null;
  device_name: string | null;
  device_code: string | null;
  region_name: string | null;
  is_lab?: number;
}

export interface DashboardSummary {
  today_events: number;
  total_events: number;
  pending_alerts: number;
  active_tracks: number;
  device_online_rate: number;
  device_health: Record<string, number>;
  device_total: number;
  trend: { hour: number; count: number }[];
  latest_alerts: {
    alert_id: number;
    alert_time: string;
    type_name: string;
    level_name: string;
    device_name: string | null;
    region_name: string | null;
  }[];
}

export interface TrackChainItem {
  chain_id: number;
  chain_unique_id: string;
  person_id: number | null;
  appearance_desc: string | null;
  is_focused: number;
  confidence: number | null;
  device_route: string;
  hop_count: number;
  first_device_name: string | null;
  last_device_name: string | null;
  chain_start_time: string | null;
  chain_end_time: string | null;
  total_duration_sec: number;
  chain_status: number;
  is_lab?: number;
}

export interface TrackDetail {
  chain_id: number;
  chain_unique_id: string;
  confidence: number | null;
  chain_start_time: string | null;
  chain_end_time: string | null;
  total_duration_sec: number;
  chain_status: number;
  person_id: number | null;
  appearance_desc: string | null;
  is_focused: number;
  items: {
    item_id: number;
    sort: number;
    device_id: number;
    device_name: string;
    device_code: string;
    region_name: string | null;
    location_text: string | null;
    appear_time: string | null;
    disappear_time: string | null;
    stay_duration_sec: number;
  }[];
}

export interface DeviceItem {
  id: number;
  device_code: string;
  device_name: string;
  device_type: string;
  location_text: string | null;
  region_code: string | null;
  region_name: string | null;
  status: string;
  health_score: number | null;
  video_quality: string | null;
  last_heartbeat_time: string | null;
  channel_count: number | null;
  ip_address: string | null;
  port: number | null;
  manufacturer: string | null;
  model: string | null;
  install_time: string | null;
  remark: string | null;
  operator_name: string | null;
}

export interface FaultItem {
  id: number;
  device_id: number;
  device_code: string;
  device_name: string;
  fault_type: string;
  fault_level: string;
  fault_desc: string | null;
  occurrence_time: string | null;
  recovery_time: string | null;
  disposal_status: string;
  assigned_name: string | null;
  repair_result: string | null;
  repair_remark: string | null;
}

export interface RepairOrderItem {
  id: number;
  order_no: string;
  fault_id: number;
  device_id: number;
  device_code: string;
  device_name: string | null;
  status: string;
  fault_type: string;
  fault_level: string;
  fault_desc: string | null;
  damage_cause: string | null;
  repair_detail: string | null;
  assigned_to: number | null;
  assigned_name: string | null;
  dispatch_strategy: string | null;
  assigned_at: string | null;
  plan_finish_time: string | null;
  started_at: string | null;
  completed_at: string | null;
  create_time: string | null;
}

export interface RepairOrderDetail extends RepairOrderItem {
  device_type: string | null;
  device_ip: string | null;
  device_location: string | null;
  device_region: string | null;
  fault_occurrence_time: string | null;
  fault_disposal_status: string | null;
  operator_name: string | null;
  dispatch_rule_desc: string | null;
  dispatch_result: string | null;
  candidate_count: number | null;
  load_snapshot: string | null;
  history: { status: string; status_name: string; time: string | null; operator: string | null }[];
  logs: { operator_name: string | null; operated_at: string | null; action: string | null; content: string | null }[];
}

export interface RepairCandidateItem {
  account_id: number;
  real_name: string;
  dept: string | null;
}

export interface RepairDispatchLogItem {
  id: number;
  order_id: number;
  fault_id: number;
  device_id: number;
  strategy: string;
  candidate_count: number;
  load_snapshot: string | null;
  winner_id: number | null;
  winner_name: string | null;
  result: string;
  remark: string | null;
  create_time: string | null;
}

export interface SimulateFaultResult {
  fault_id: number;
  order_id: number;
  order_no: string;
  assigned_to: number | null;
  assigned_name: string | null;
}

export interface PersonItem {
  person_id: number;
  appearance_desc: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  is_focused: number;
  risk_level_id: number | null;
  matched_user_id: number | null;
  matched_user_name: string | null;
  match_confidence: number | null;
  behavior_count: number;
  track_count: number;
}

export interface LogItem {
  log_id: number;
  module_code: string;
  operation_type: string;
  operator_id: number | null;
  operator_name: string | null;
  operator_role: string | null;
  target_id: number | null;
  target_type: string | null;
  operation_content: string | null;
  operated_at: string | null;
}

export interface AccountItem {
  account_id: number;
  login_name: string;
  real_name: string;
  dept: string | null;
  phone: string | null;
  type_id: number;
  type_name: string;
  status: number;
  use_custom?: number;
  last_login_time: string | null;
}

export interface RoleItem {
  type_id: number;
  type_name: string;
  type_desc: string | null;
  is_super: boolean;
  account_count: number;
  perm_ids: number[];
}

export interface PermItem {
  perm_id: number;
  perm_name: string;
  perm_key: string;
  perm_type: number;
  parent_id: number;
  sort: number;
}

export interface AccountPermInfo {
  use_custom: number;
  custom_perm_ids: number[];
  role_perm_ids: number[];
  effective_perm_ids: number[];
}

export interface PersonDetail extends PersonItem {
  recent_behaviors: {
    behavior_id: number;
    detected_at: string;
    type_name: string;
    level_name: string;
    status_name: string;
    description: string | null;
    confidence_score: number | null;
    track_id: number | null;
    device_name: string | null;
    region_name: string | null;
  }[];
}

export interface LabPublishResponse {
  record_id: number;
  published: boolean;
  counts: {
    behavior_count: number;
    alert_count: number;
    work_order_count: number;
  };
}

export interface LabRecordItem {
  record_id: number;
  record_name: string;
  device_id: number | null;
  video_filename: string;
  event_count: number;
  track_count: number;
  is_published: number;
  create_time: string | null;
}

export interface LabRecordDetail extends LabRecordItem {
  result: any;
}

export interface DataIndexSummary {
  total: {
    behavior_count: number;
    track_count: number;
    alert_count: number;
    work_order_count: number;
    person_count: number;
    device_count: number;
  };
  type_distribution: { id: number; name: string; value: number }[];
  region_distribution: { name: string; value: number }[];
  seven_day_trend: { date: string; count: number }[];
}

export interface BackupItem {
  backup_id: number;
  backup_name: string;
  backup_type: string;
  strategy_desc: string | null;
  file_path: string;
  file_size: number;
  status: string;
  operator_id: number | null;
  operator_name: string | null;
  create_time: string | null;
}

export interface RestoreLogItem {
  restore_id: number;
  backup_id: number;
  backup_name: string | null;
  restore_status: string;
  result_msg: string | null;
  operator_id: number | null;
  operator_name: string | null;
  restore_time: string | null;
}

export const api = {
  login: (login_name: string, password: string) => http.post<LoginResult>("/auth/login", { login_name, password }),
  register: (body: { real_name: string; login_name: string; password: string; type_id: number }) =>
    http.post("/auth/register", body),
  me: () => http.get<Omit<LoginResult, "token">>("/auth/me"),
  registerRoles: () => http.get<EnumOption[]>("/auth/roles"),
  enums: () => http.get<MetaEnums>("/meta/enums"),
  publicEnums: () => http.get<MetaEnums>("/meta/enums"),
  dashboard: () => http.get<DashboardSummary>("/dashboard/summary", { ...getLabIncludeParam() }),
  todoCount: () => http.get<{ count: number }>("/alerts/todo-count", { ...getLabIncludeParam() }),
  alerts: (params: { status_id?: number; severity_id?: number; keyword?: string; page: number; size: number }) =>
    http.get<PageData<AlertItem>>("/alerts", { ...params, ...getLabIncludeParam() }),
  confirmAlert: (alertId: number) => http.post(`/alerts/${alertId}/confirm`),
  ignoreAlert: (alertId: number, note?: string) => http.post(`/alerts/${alertId}/ignore`, { note }),
  workOrders: (params: { status_id?: number; page: number; size: number }) =>
    http.get<PageData<WorkOrderItem>>("/workorders", { ...params, ...getLabIncludeParam() }),
  workOrderDetail: (id: number) => http.get<WorkOrderDetail>(`/workorders/${id}`),
  createWorkOrder: (alert_id: number, assigned_to: number) => http.post("/workorders", { alert_id, assigned_to }),
  handleWorkOrder: (id: number, handle_result: string) => http.put(`/workorders/${id}/handle`, { handle_result }),
  closeWorkOrder: (id: number) => http.put(`/workorders/${id}/close`),
  behaviors: (params: {
    type_id?: number;
    severity_id?: number;
    status_id?: number;
    camera_id?: number;
    region_name?: string;
    start_time?: string;
    end_time?: string;
    keyword?: string;
    page: number;
    size: number;
  }) => http.get<PageData<BehaviorItem>>("/behaviors", { ...params, ...getLabIncludeParam() }),
  tracks: (params: { chain_status?: number; keyword?: string; start_time?: string; end_time?: string; page: number; size: number }) =>
    http.get<PageData<TrackChainItem>>("/tracks", { ...params, ...getLabIncludeParam() }),
  trackDetail: (chainId: number) => http.get<TrackDetail>(`/tracks/${chainId}`),
  devices: (params: { status?: string; device_type?: string; keyword?: string; page: number; size: number }) =>
    http.get<PageData<DeviceItem>>("/devices", params),
  createDevice: (body: Partial<DeviceItem> & { device_code: string; device_name: string }) => http.post("/devices", body),
  updateDevice: (id: number, body: Partial<DeviceItem>) => http.put(`/devices/${id}`, body),
  faults: (params: { device_id?: number; disposal_status?: string; page: number; size: number }) =>
    http.get<PageData<FaultItem>>("/devices/faults/list", params),
  closeFault: (id: number) => http.put(`/devices/faults/${id}/close`),
  simulateFault: (id: number, body: { fault_type?: string; fault_level?: string; fault_desc?: string }) =>
    http.post<SimulateFaultResult>(`/devices/${id}/simulate-fault`, body),
  repairOrders: (params: {
    status?: string;
    keyword?: string;
    fault_id?: number;
    assigned_to?: number;
    start_time?: string;
    end_time?: string;
    only_mine?: boolean;
    page: number;
    size: number;
  }) => http.get<PageData<RepairOrderItem>>("/devices/repair-orders", { ...params, only_mine: params.only_mine ? "true" : undefined }),
  repairOrderDetail: (id: number) => http.get<RepairOrderDetail>(`/devices/repair-orders/${id}`),
  repairCandidates: () => http.get<RepairCandidateItem[]>("/devices/repair-candidates"),
  acceptRepairOrder: (id: number) => http.post(`/devices/repair-orders/${id}/accept`),
  finishRepairOrder: (id: number, body: { damage_cause: string; repair_detail: string }) =>
    http.put(`/devices/repair-orders/${id}/finish`, body),
  repairDispatchLogs: (params: { order_id?: number; page: number; size: number }) =>
    http.get<PageData<RepairDispatchLogItem>>("/devices/repair-orders/dispatch-logs", params),
  persons: (params: { keyword?: string; is_focused?: number; page: number; size: number }) =>
    http.get<PageData<PersonItem>>("/persons", { ...params, ...getLabIncludeParam() }),
  togglePersonFocus: (personId: number, is_focused: number) => http.put(`/persons/${personId}/focus`, { is_focused }),
  exportPersons: (params: { keyword?: string; is_focused?: number }) =>
    http.download("/persons/export", { ...params, ...getLabIncludeParam() }, "anonymous_persons.csv"),
  logs: (params: { module_code?: string; operation_type?: string; keyword?: string; start_time?: string; end_time?: string; page: number; size: number }) =>
    http.get<PageData<LogItem>>("/logs", params),
  exportLogs: (params: { module_code?: string; operation_type?: string; keyword?: string; start_time?: string; end_time?: string }) =>
    http.download("/logs/export", params, "operation_logs.csv"),
  accounts: (params: { keyword?: string; type_id?: number; status?: number; page: number; size: number }) =>
    http.get<PageData<AccountItem>>("/system/accounts", params),
  createAccount: (body: { login_name: string; password: string; real_name: string; dept?: string; phone?: string; type_id: number }) =>
    http.post("/system/accounts", body),
  toggleAccountStatus: (accountId: number, status: number) => http.put(`/system/accounts/${accountId}/status`, { status }),
  accountPermissions: (accountId: number) => http.get<AccountPermInfo>(`/system/accounts/${accountId}/permissions`),
  saveAccountPermissions: (accountId: number, body: { use_custom: number; perm_ids: number[] }) =>
    http.put<void>(`/system/accounts/${accountId}/permissions`, body),
  deleteAccount: (accountId: number) => http.delete<void>(`/system/accounts/${accountId}`),
  roles: () => http.get<RoleItem[]>("/system/roles"),
  permissions: () => http.get<PermItem[]>("/system/permissions"),
  saveRolePermissions: (typeId: number, perm_ids: number[]) => http.put(`/system/roles/${typeId}/permissions`, { perm_ids }),
  deleteRole: (typeId: number) => http.delete<void>(`/system/roles/${typeId}`),
  createRole: (body: { type_name: string; type_desc?: string }) => http.post<{ type_id: number }>("/system/roles", body),
  dataIndex: () => http.get<DataIndexSummary>("/dashboard/data-index", { ...getLabIncludeParam() }),
  personDetail: (personId: number) => http.get<PersonDetail>(`/persons/${personId}`),
  exportBehaviors: (params: { type_id?: number; severity_id?: number; status_id?: number; camera_id?: number; region_name?: string; start_time?: string; end_time?: string; keyword?: string }) =>
    http.download("/behaviors/export", params, "abnormal_behaviors.csv"),
  exportTracks: (params: { chain_status?: number; keyword?: string; start_time?: string; end_time?: string }) =>
    http.download("/tracks/export", params, "track_chains.csv"),
  exportAlerts: (params: { status_id?: number; severity_id?: number; keyword?: string }) =>
    http.download("/alerts/export", params, "behavior_alerts.csv"),
  labPublishResult: (body: { device_id?: number; record_name?: string; video_filename?: string; result: any }) =>
    http.post<LabPublishResponse>("/lab/publish", body),
  labClearSandbox: () => http.post<{ cleared: boolean }>("/lab/clear-sandbox"),
  labRecords: (params: { page: number; size: number }) => http.get<PageData<LabRecordItem>>("/lab/records", params),
  labRecordDetail: (id: number) => http.get<LabRecordDetail>(`/lab/records/${id}`),
  labRecordPublish: (id: number) => http.post<{ published: boolean }>(`/lab/records/${id}/publish`),
  labRecordUnpublish: (id: number) => http.post<{ unpublished: boolean }>(`/lab/records/${id}/unpublish`),
  labRecordDelete: (id: number) => http.delete<{ deleted: boolean }>(`/lab/records/${id}`),
  backups: (params: { page?: number; size?: number; backup_type?: string; status?: string }) =>
    http.get<PageData<BackupItem>>("/backups", params),
  createBackup: (body: { backup_type?: "MANUAL" | "AUTO"; strategy_desc?: string } = {}) =>
    http.post<BackupItem>("/backups", body),
  deleteBackup: (backupId: number) => http.delete<void>(`/backups/${backupId}`),
  restoreBackup: (backupId: number) => http.post<void>(`/backups/${backupId}/restore`),
  restoreLogs: (params: { page?: number; size?: number }) => http.get<PageData<RestoreLogItem>>("/backups/restore-logs", params),
};
