const BASE_URL = "/api/v1";

export class ApiError extends Error {
  code: number;
  status: number;
  constructor(message: string, code: number, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function getToken(): string {
  return localStorage.getItem("token") || "";
}

function formatError(payload: any, status: number): string {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return `请求失败（${status}）`;
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  if (options.body instanceof FormData) {
    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(options.method || "GET", `${BASE_URL}${path}`);
      if (headers["Authorization"]) {
        xhr.setRequestHeader("Authorization", headers["Authorization"]);
      }
      xhr.onload = () => {
        const text = xhr.responseText || "";
        const payload = text ? JSON.parse(text) : null;
        if (xhr.status === 401) {
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          if (!window.location.pathname.startsWith("/login")) {
            window.location.href = "/login";
          }
          reject(new ApiError("登录状态已失效，请重新登录", 401, 401));
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new ApiError(formatError(payload, xhr.status), payload?.code ?? xhr.status, xhr.status));
          return;
        }
        if (payload && typeof payload === "object" && "code" in payload) {
          if (payload.code !== 0) {
            reject(new ApiError(payload.message || "请求失败", payload.code, xhr.status));
          } else {
            resolve(payload.data as T);
          }
        } else {
          resolve(payload as T);
        }
      };
      xhr.onerror = () => reject(new ApiError("网络请求失败", 0, 0));
      xhr.onabort = () => reject(new ApiError("请求已取消", 0, 0));
      xhr.send(options.body as FormData);
    });
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError("登录状态已失效，请重新登录", 401, 401);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(formatError(payload, response.status), payload?.code ?? response.status, response.status);
  }
  if (payload && typeof payload === "object" && "code" in payload) {
    if (payload.code !== 0) throw new ApiError(payload.message || "请求失败", payload.code, response.status);
    return payload.data as T;
  }
  return payload as T;
}

async function download(path: string, params: Record<string, string | number | undefined | null>, fallbackName: string): Promise<void> {
  let url = `${BASE_URL}${path}`;
  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join("&");
  if (query) url += `?${query}`;
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(url, { headers });
  if (!response.ok) throw new ApiError(`导出失败（${response.status}）`, response.status, response.status);
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename=([^;]+)/);
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = match?.[1]?.trim() || fallbackName;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

export const http = {
  download,
  get<T = any>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
    let url = path;
    if (params) {
      const query = Object.entries(params)
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
        .join("&");
      if (query) url += `?${query}`;
    }
    return request<T>(url);
  },
  post<T = any>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  },
  put<T = any>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });
  },
  upload<T = any>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, { method: "POST", body: formData });
  },
  delete<T = any>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};
