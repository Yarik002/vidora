/**
 * Thin fetch wrapper.
 * - auth lives in httpOnly cookies, JS never sees the tokens;
 * - every unsafe request carries X-CSRF-Token copied from the readable `vid_csrf` cookie;
 * - on 401 the access token is refreshed once (shared promise, so parallel requests
 *   don't start several refreshes) and the request is retried.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";

export function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)vid_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

let refreshing: Promise<boolean> | null = null;
let onSessionExpired: (() => void) | null = null;

export function setSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken() },
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

interface Options {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  retry?: boolean;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const { method = "GET", body, signal, retry = true } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();

  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
    signal,
  });

  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) return api<T>(path, { ...opts, retry: false });
    onSessionExpired?.();
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Ошибка ${res.status}`;
    let details: unknown;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
      details = data?.error?.details;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Human-readable Russian message for common API errors. */
export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    const known: Record<string, string> = {
      invalid_credentials: "Неверный логин или пароль",
      email_taken: "Этот email уже зарегистрирован",
      username_taken: "Это имя пользователя уже занято",
      rate_limited: "Слишком много попыток, подождите минуту",
      account_disabled: "Аккаунт заблокирован",
      csrf_failed: "Сессия устарела, обновите страницу",
      upload_too_large: "Файл слишком большой",
      video_not_found: "Видео не найдено или доступ к нему ограничен",
      user_not_found: "Пользователь не найден",
      validation_error: "Проверьте правильность заполнения полей",
      unauthorized: "Нужно войти в аккаунт",
    };
    return known[err.code] ?? err.message;
  }
  if (err instanceof DOMException && err.name === "AbortError") return "";
  return "Нет связи с сервером";
}
