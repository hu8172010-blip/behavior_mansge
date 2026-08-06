/**
 * 远端模型推理服务（FastAPI）访问模块。
 * 开发环境通过 Vite 代理 /model → http://192.168.237.123:8010，生产环境走同源/Nginx 中转，
 * 禁止浏览器直接跨域请求模型服务。
 */

const MODEL_BASE = "/model";

export const MODEL_OFFLINE_MSG =
  "模型推理服务离线，请检查192.168.237.123设备是否开机、8010端口防火墙放行";

export class ModelApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** 兼容 FastAPI 标准 detail 报错与 job 内 error.message 报错 */
export async function readApiError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
    if (typeof payload?.error?.message === "string") return payload.error.message;
  } catch (_) {
    // 非 JSON 响应继续返回通用错误
  }
  return `请求失败：HTTP ${response.status}`;
}

/** 按 HTTP 状态码生成面向用户的友好提示（不暴露内部路径与堆栈） */
export function modelErrorMessage(status: number, fallback: string): string {
  switch (status) {
    case 400:
      return `视频文件异常：${fallback}`;
    case 404:
      return "任务已失效或不存在，请重新上传";
    case 409:
      return "任务状态冲突（可能仍在处理或关联中），请稍后重试";
    case 413:
      return "视频超过 2GB 上传上限，请压缩或裁剪后重试";
    case 422:
      return "请求参数或校准配置（calibration）错误，请检查后重试";
    case 503:
      return "推理服务繁忙（同时最多 2 路处理、队列上限 8 个），请稍后重试";
    case 507:
      return "模型电脑运行目录空间不足，请联系模型电脑负责人清理空间";
    default:
      return fallback;
  }
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${MODEL_BASE}${path}`, options);
  } catch (_) {
    throw new ModelApiError(MODEL_OFFLINE_MSG, 0);
  }
  // 204 删除成功：没有 JSON 响应体
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const raw = await readApiError(response);
    throw new ModelApiError(modelErrorMessage(response.status, raw), response.status);
  }
  return response.json() as Promise<T>;
}

/* ------------------------------ 类型定义 ------------------------------ */

export type ModelJobStatus = "queued" | "processing" | "completed" | "failed";

export interface ModelJob {
  job_id: string;
  status: ModelJobStatus;
  progress: number;
  original_name?: string | null;
  error?: { code?: string; message?: string } | null;
  model_status?: unknown;
  result_url?: string | null;
  video_url?: string | null;
}

export interface ModelEvent {
  event_type: string;
  start_time: number;
  end_time: number;
  confidence: number;
  track_ids: number[];
  requires_review?: boolean;
  evidence?: Record<string, unknown>;
}

export interface ModelTrackPoint {
  timestamp: number;
  x: number;
  y: number;
}

export interface ModelTrack {
  track_id: number;
  generation: number;
  abnormal?: boolean;
  event_types: string[];
  first_seen: number;
  last_seen: number;
  path_length_px?: number;
  net_displacement_px?: number;
  points: ModelTrackPoint[];
}

export interface ClassifierPrediction {
  track_id: number;
  start_time: number;
  end_time: number;
  status: string;
  smoothed_probabilities: { normal: number; violence: number; fall: number };
  evidence?: { source?: string; requires_review?: boolean };
}

export interface ModelResult {
  video?: {
    source_name?: string;
    fps?: number;
    width?: number;
    height?: number;
    frames_processed?: number;
    duration_seconds?: number;
  };
  summary?: {
    people_tracked?: number;
    events_detected?: number;
    requires_human_review?: boolean;
    classifier_prediction_records?: number;
  };
  model_status?: unknown;
  tracking_status?: unknown;
  classifier_predictions?: ClassifierPrediction[];
  events: ModelEvent[];
  tracks: ModelTrack[];
}

export interface CollectionInfo {
  collection_id: string;
  videos?: unknown[];
  resolved?: boolean;
  status?: string;
}

export interface TrackletMatch {
  track_id: number;
  decision: string;
  global_person_id: string | null;
  similarity: number | null;
  runner_up: number | null;
  margin: number | null;
  sample_count: number | null;
  model_name?: string;
  checkpoint_sha256?: string;
  requires_review?: boolean;
}

export interface CollectionVideo {
  job_id: string;
  original_name: string;
  status: string;
  tracklets?: TrackletMatch[];
}

export interface TrajectorySegment {
  job_id: string;
  track_id: number;
  generation: number;
  start_time: number;
  end_time: number;
  points: ModelTrackPoint[];
}

export interface CollectionPerson {
  global_person_id: string;
  trajectory_segments: TrajectorySegment[];
  events?: unknown[];
}

export interface CollectionResult {
  collection_id: string;
  reid_status: string;
  reid_model?: { model_name?: string; checkpoint_sha256?: string; threshold_source?: string };
  persons: CollectionPerson[];
  videos: CollectionVideo[];
  review_candidates?: unknown[];
}

/* ------------------------------ 资源限制 ------------------------------ */

export const ALLOWED_VIDEO_EXTS = ["mp4", "avi", "mov", "mkv", "webm"];
export const MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024; // 2 GiB
export const MODEL_QUEUE_HINT =
  "模型服务最多同时处理 2 路任务、队列上限 8 个，超出将排队等待；服务端任务结果仅自动保留 24 小时，重要结果请手动导出。";

export function validateVideoFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() || "";
  if (!ALLOWED_VIDEO_EXTS.includes(ext)) return "仅支持 MP4 / AVI / MOV / MKV / WEBM 格式视频";
  if (file.size > MAX_VIDEO_BYTES) return "单个视频不能超过 2GB";
  return null;
}

/* ------------------------------ 接口封装 ------------------------------ */

export const modelHealth = () => request<{ status: string }>("/health");

export const modelCreateJob = (video: File, calibration?: string) => {
  const form = new FormData();
  form.append("video", video);
  if (calibration) form.append("calibration", calibration);
  return request<ModelJob>("/api/jobs", { method: "POST", body: form });
};

export const modelGetJob = (jobId: string) => request<ModelJob>(`/api/jobs/${jobId}`);

export const modelGetResult = (jobId: string) => request<ModelResult>(`/api/jobs/${jobId}/result`);

export const modelDeleteJob = (jobId: string) =>
  request<void>(`/api/jobs/${jobId}`, { method: "DELETE" });

export const modelJobVideoUrl = (jobId: string) => `${MODEL_BASE}/api/jobs/${jobId}/video`;

export const modelCreateCollection = () =>
  request<CollectionInfo>("/api/collections", { method: "POST" });

export const modelUploadCollectionVideo = (collectionId: string, video: File) => {
  const form = new FormData();
  form.append("video", video);
  return request<ModelJob>(`/api/collections/${collectionId}/videos`, { method: "POST", body: form });
};

export const modelResolveCollection = (collectionId: string) =>
  request<CollectionResult>(`/api/collections/${collectionId}/resolve-identities`, { method: "POST" });

export const modelGetCollectionResult = (collectionId: string) =>
  request<CollectionResult>(`/api/collections/${collectionId}/result`);

export const modelDeleteCollection = (collectionId: string) =>
  request<void>(`/api/collections/${collectionId}`, { method: "DELETE" });

/* ------------------------------ 轮询工具 ------------------------------ */

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 轮询任务直至完成/失败。默认 1500ms 一次，全局超时 30 分钟；
 * 超时仅提示，不中断远端模型后台推理。
 */
export async function pollModelJob(
  jobId: string,
  onUpdate?: (job: ModelJob) => void,
  timeoutMs = 30 * 60 * 1000,
): Promise<ModelJob> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await modelGetJob(jobId);
    onUpdate?.(job);
    if (job.status === "completed") return job;
    if (job.status === "failed") {
      throw new ModelApiError(job.error?.message || "视频处理失败", 0);
    }
    await sleep(1500);
  }
  throw new ModelApiError("等待超时：任务可能仍在模型电脑继续执行，可稍后重试查询", 0);
}
