export type LogEvent = {
  timestamp: string;
  ts_unix?: number | null;
  source: string;
  level: string;
  job_id?: number | null;
  event_type: string;
  message: string;
};

export type LogsResponse = {
  events: LogEvent[];
  total: number;
  page: number;
  total_pages: number;
  q: string;
  level: string;
  source: string;
};
