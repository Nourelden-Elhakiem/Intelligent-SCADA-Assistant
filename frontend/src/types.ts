export interface Health {
  status: "ok" | "degraded";
  version: string;
  database: "connected" | "unavailable" | "not_configured";
  answer_model: "configured" | "not_configured";
  default_document: "indexed" | "not_indexed" | "unavailable";
  default_pdf: "available" | "missing";
  knowledge_base: "ready" | "default_not_indexed" | "database_unavailable" | "database_not_configured";
}

export interface Runtime {
  version: string;
  embedding_model: string;
  embedding_dimension: number;
  answer_model: string;
  router_enabled: boolean;
  default_top_k: number;
  max_top_k: number;
  max_upload_mb: number;
  images_enabled: boolean;
  memory_enabled: boolean;
  default_document_key: string;
  default_document_name: string;
  default_pdf_path: string;
  min_retrieval_score: number;
}

export interface DocumentSummary {
  document_key: string;
  document_name: string;
  source_filename: string;
  embedding_model: string;
  embedding_dimension: number;
  chunk_count: number;
  image_count: number;
  created_at: string;
  updated_at: string;
  is_default: boolean;
}

export interface Citation {
  source_id: string;
  chunk_id: string;
  label: string;
  page_start: number;
  page_end: number;
  section_path: string[];
}

export interface Source {
  chunk_id: string;
  text: string;
  page_start: number;
  page_end: number;
  source_pages: number[];
  section_title: string;
  section_path: string[];
  score: number;
}

export interface RelatedImage {
  filename: string;
  page: number;
  width: number;
  height: number;
  file_size_bytes: number;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  sources: Source[];
  related_images: RelatedImage[];
  session_id: string | null;
  routing: Record<string, unknown>;
}

export interface Job {
  job_id: string;
  document_key: string;
  document_name: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface ChatMessage {
  documentKey: string;
  documentName: string;
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: Date;
  citations?: Citation[];
  sources?: Source[];
  images?: RelatedImage[];
  routing?: Record<string, unknown>;
  error?: boolean;
}
