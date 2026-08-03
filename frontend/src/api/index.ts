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

export interface AnalyzeResult {
  result: {
    events: any[];
    tracks: any[];
    summary: any;
  };
  record_id: number | null;
  counts?: {
    behavior_count: number;
    alert_count: number;
    work_order_count: number;
  };
}

export interface LabJobCreateResult {
  job_id: string;
  record_id: number | null;
}

export interface LabJobStatus {
  job_id: string;
  status: string;
  progress: number;
  result: any;
  error: string | null;
  published: boolean;
}

export interface LabPublishResult {
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
  type_distribution: { name: string; value: number }[];
  region_distribution: { name: string; value: number }[];
  seven_day_trend: { date: string; count: number }[];
}

export const api = {
  login: (login_name: string, password: string) => http.post<LoginResult>("/auth/login", { login_name, password }),
  register: (body: { real_name: string; login_name: string; password: string; type_id: number }) =>
    http.post("/auth/register", body),
  me: () => http.get<Omit<LoginResult, "token">>("/auth/me"),
  registerRoles: () => http.get<EnumOption[]>("/auth/roles"),
  enums: () => http.get<MetaEnums>("/meta/enums"),
  publicEnums: () => http.get<MetaEnums>("/meta/enums"),
  dashboard: () => http.get<DashboardSummary>("/dashboard/summary"),
  todoCount: () => http.get<{ count: number }>("/alerts/todo-count"),
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
  persons: (params: { keyword?: string; is_focused?: number; page: number; size: number }) =>
    http.get<PageData<PersonItem>>("/persons", { ...params, ...getLabIncludeParam() }),
  togglePersonFocus: (personId: number, is_focused: number) => http.put(`/persons/${personId}/focus`, { is_focused }),
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
  dataIndex: () => http.get<DataIndexSummary>("/dashboard/data-index"),
  personDetail: (personId: number) => http.get<PersonDetail>(`/persons/${personId}`),
  exportBehaviors: (params: { type_id?: number; severity_id?: number; status_id?: number; camera_id?: number; keyword?: string }) =>
    http.download("/behaviors/export", params, "abnormal_behaviors.csv"),
  exportTracks: (params: { chain_status?: number; keyword?: string; start_time?: string; end_time?: string }) =>
    http.download("/tracks/export", params, "track_chains.csv"),
  exportAlerts: (params: { status_id?: number; severity_id?: number; keyword?: string }) =>
    http.download("/alerts/export", params, "behavior_alerts.csv"),
  labAnalyze: (video: File, device_id: number, calibration: string, mode: "temp" | "persist", record_name?: string) => {
    const form = new FormData();
    form.append("video", video);
    form.append("device_id", String(device_id));
    form.append("calibration", calibration);
    form.append("mode", mode);
    if (record_name) form.append("record_name", record_name);
    return http.upload<AnalyzeResult>("/lab/analyze", form);
  },
  labJobCreate: (video: File, device_id: number, calibration: string, mode: "temp" | "persist" = "temp", record_name?: string) => {
    const form = new FormData();
    form.append("video", video);
    form.append("device_id", String(device_id));
    form.append("calibration", calibration);
    form.append("mode", mode);
    if (record_name) form.append("record_name", record_name);
    return http.upload<LabJobCreateResult>("/lab/jobs", form);
  },
  labJobGet: (job_id: string) => http.get<LabJobStatus>(`/lab/jobs/${job_id}`),
  labJobPublish: (job_id: string) => http.post<LabPublishResult>(`/lab/jobs/${job_id}/publish`),
  labClearSandbox: () => http.post<{ cleared: boolean }>("/lab/clear-sandbox"),
  inferenceJob: (video: File, device_id: number, calibration: string) => {
    const form = new FormData();
    form.append("video", video);
    form.append("device_id", String(device_id));
    form.append("calibration", calibration);
    return http.upload<{ behavior_count: number; alert_count: number; work_order_count: number }>("/inference/jobs", form);
  },
  labRecords: (params: { page: number; size: number }) => http.get<PageData<LabRecordItem>>("/lab/records", params),
  labRecordDetail: (id: number) => http.get<LabRecordDetail>(`/lab/records/${id}`),
  labRecordPublish: (id: number) => http.post<{ published: boolean }>(`/lab/records/${id}/publish`),
  labRecordUnpublish: (id: number) => http.post<{ unpublished: boolean }>(`/lab/records/${id}/unpublish`),
  labRecordDelete: (id: number) => http.delete<{ deleted: boolean }>(`/lab/records/${id}`),
};
