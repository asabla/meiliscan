// API client for Meiliscan REST API

export interface HealthResponse {
  status: string;
  version: string;
  uptime: string;
}

export interface AnalyzeRequest {
  url: string;
  api_key?: string;
}

export interface Report {
  generated_at: string;
  version: string;
  source: Source;
  instance: InstanceInfo;
  findings: Finding[];
  summary: Summary;
}

export interface Source {
  type: "live" | "dump";
  url?: string;
  dump_path?: string;
}

export interface InstanceInfo {
  version?: string;
  index_count?: number;
  total_documents?: number;
  database_size?: number;
}

export interface Finding {
  id: string;
  title: string;
  description: string;
  severity: "critical" | "warning" | "suggestion" | "info";
  category: string;
  index_uid?: string;
  details?: Record<string, unknown>;
  recommendation?: string;
  fix_command?: string;
  timestamp: string;
}

export interface Summary {
  health_score: number;
  health_status: "healthy" | "warning" | "critical";
  total_findings: number;
  critical_count: number;
  warning_count: number;
  suggestion_count: number;
  info_count: number;
}

export interface ProgressEvent {
  type: "progress" | "complete" | "error";
  message: string;
  progress?: number;
  data?: Report;
}

export class MeiliscanAPI {
  constructor(private baseURL: string = "http://localhost:8080") {}

  async health(): Promise<HealthResponse> {
    const res = await fetch(`${this.baseURL}/api/health`);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  }

  async analyze(request: AnalyzeRequest): Promise<Report> {
    const res = await fetch(`${this.baseURL}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || `API error: ${res.status}`);
    }
    return res.json();
  }

  async *analyzeStream(
    request: AnalyzeRequest
  ): AsyncGenerator<ProgressEvent, void, unknown> {
    const res = await fetch(`${this.baseURL}/api/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || `API error: ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data) {
            yield JSON.parse(data) as ProgressEvent;
          }
        }
      }
    }
  }
}
