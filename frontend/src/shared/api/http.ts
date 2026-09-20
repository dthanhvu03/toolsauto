/** FastAPI cookie-auth: JSON 401 when the Vite origin has no session. */
export function redirectToLoginIfUnauthorized(status: number) {
  if (status === 401 && typeof window !== "undefined") {
    window.location.assign("/login");
  }
}

/** Shared fetch helper for same-origin JSON APIs (cookie session). */
export async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin" });
  if (r.status === 401) {
    redirectToLoginIfUnauthorized(401);
    throw new Error(`${url} → 401`);
  }
  if (!r.ok) throw new Error(await errorMessage(r, url));
  return r.json() as Promise<T>;
}

export type OkMessage = { ok: boolean; message: string; id?: number };

async function errorMessage(r: Response, url: string): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.error === "string") return body.error;
    if (typeof body?.message === "string") return body.message;
  } catch {
    /* ignore */
  }
  return `${url} → ${r.status}`;
}

export async function sendJson<T = OkMessage>(
  url: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown
): Promise<T> {
  const r = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) {
    redirectToLoginIfUnauthorized(401);
    throw new Error(`${url} → 401`);
  }
  if (!r.ok) throw new Error(await errorMessage(r, url));
  if (r.status === 204) return { ok: true, message: "OK" } as T;
  return r.json() as Promise<T>;
}

export async function sendForm<T = OkMessage>(url: string, form: FormData): Promise<T> {
  const r = await fetch(url, { method: "POST", credentials: "same-origin", body: form });
  if (r.status === 401) {
    redirectToLoginIfUnauthorized(401);
    throw new Error(`${url} → 401`);
  }
  if (!r.ok) throw new Error(await errorMessage(r, url));
  return r.json() as Promise<T>;
}
