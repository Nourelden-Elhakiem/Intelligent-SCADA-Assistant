import type {
  AskResponse,
  DocumentSummary,
  Health,
  Job,
  Runtime,
} from "./types";

const API_ROOT = "/api/v1";

interface ApiErrorBody {
  detail?: string;
  error?: { message?: string };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // A reverse proxy may return a non-JSON error page.
    }
    throw new Error(
      body.error?.message || body.detail || `Request failed with status ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  runtime: () => request<Runtime>("/runtime"),
  documents: async () => (await request<{ documents: DocumentSummary[] }>("/documents")).documents,
  job: (jobId: string) => request<Job>(`/jobs/${encodeURIComponent(jobId)}`),
  upload: (form: FormData) =>
    request<Job>("/documents/upload", { method: "POST", body: form }),
  ask: (payload: {
    question: string;
    document_key?: string | null;
    session_id: string | null;
    memory_enabled: boolean;
    include_images: boolean;
    top_k: number | null;
  }, signal?: AbortSignal) => request<AskResponse>("/chat/ask", { method: "POST", body: JSON.stringify(payload), signal }),
  deleteDocument: (documentKey: string) =>
    request<{ deleted: boolean; artifacts_deleted: boolean }>(
      `/documents/${encodeURIComponent(documentKey)}?delete_artifacts=true`,
      { method: "DELETE" },
    ),
  imageUrl: (documentKey: string, filename: string) =>
    `${API_ROOT}/documents/${encodeURIComponent(documentKey)}/images/${encodeURIComponent(filename)}`,
};
