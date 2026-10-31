export type ProjectStatus =
  | "DRAFT"
  | "RENDERING"
  | "RENDERED"
  | "REVIEW"
  | "APPROVED"
  | "SCHEDULED"
  | "POSTED"
  | "FAILED"
  | "REJECTED";

export type ProjectRow = {
  id: number;
  status: ProjectStatus;
  channel: string | null;
  channel_id: number | null;
  caption: string | null;
  hashtags: string[];
  duration: number | null;
  error: string | null;
  viral_material_id: number | null;
  created_at: number;
  rendered_at: number | null;
  approved_at: number | null;
  has_video: boolean;
  /** biến thể A/B → dự án gốc */
  parent_project_id: number | null;
  /** kỹ thuật đang dùng: nguồn, mẫu, lật, màu, cắt, phụ đề, lồng tiếng, hook, nhạc, logo… */
  tags: string[];
};

export type ProjectsResponse = {
  projects: ProjectRow[];
  counts: Partial<Record<ProjectStatus, number>>;
  tasks_pending: number;
};

export type ClipAudio = { asset: number; volume: number };
export type Clip = { asset: number; start: number; end: number | null; audio: ClipAudio[]; hflip: boolean };
export type SubLine = { start: number; end: number; text: string };
export type TextOverlay = { text: string; start: number; end: number | null; pos: "top" | "center" | "bottom"; size: number };
export type AudioTrack = { asset: number; volume: number; start: number; loop: boolean };

/** Đúng hình `app/features/studio/spec.py` — server từ chối trường lạ (extra="forbid"). */
export type ProjectSpec = {
  v: 1;
  canvas: { w: number; h: number; fps: number; fit: "blur_pad" | "crop" | "pad"; lut: string | null };
  clips: Clip[];
  subtitles: {
    enabled: boolean;
    source: "transcript" | "dub" | "lines";
    lines: SubLine[];
    edits: Record<string, string>;
    font_size: number;
    margin_v: number;
    max_chars: number;
  };
  texts: TextOverlay[];
  audio: { original: number; tracks: AudioTrack[] };
  logo: { asset: number; pos: "tl" | "tr" | "bl" | "br"; width: number } | null;
  credit: string | null;
};

export type Asset = {
  id: number;
  kind: "video" | "audio" | "image";
  origin: string;
  title: string | null;
  credit: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean | null;
  source_url: string | null;
  created_at: number;
};

export type ProjectDetail = {
  project: {
    id: number;
    status: ProjectStatus;
    caption: string | null;
    hashtags: string[];
    duration: number | null;
    error: string | null;
    rendered_at: number | null;
    approved_at: number | null;
    viral_material_id: number | null;
    editable: boolean;
    tags: string[];
  };
  spec: ProjectSpec;
  asset: Asset | null;
  assets: Asset[];
  channel: { id: number; name: string } | null;
  template: { id: number; name: string; kind: string } | null;
  subtitle_lines: SubLine[];
  luts: string[];
  /** false với video reup — không lật gương / không biến thể (ADR-061 mục 11) */
  variants_allowed: boolean;
  group: {
    root_id: number;
    members: { id: number; status: ProjectStatus; look: [boolean, string | null]; is_root: boolean }[];
  };
  tasks: { id: number; stage: string; status: string; error: string | null }[];
};

export type Channel = {
  id: number;
  buffer_channel_id: string;
  name: string;
  template_id: number | null;
  auto_approve: boolean;
  show_credit: boolean;
  take_reup: boolean;
  active: boolean;
  logo_asset_id: number | null;
  intro_asset_id: number | null;
  outro_asset_id: number | null;
  /** Giọng VieNeu khi lồng tiếng; null = theo mẫu (nữ / nam). */
  dub_voice: string | null;
};

/** Tiến trình (PLAN-114): một bước của một việc. */
export type JobStep = {
  stage: string;
  label: string;
  status: "pending" | "queued" | "running" | "retry" | "done" | "skipped" | "failed" | "waiting" | "cancelled";
  note: string | null;
  started_at: number | null;
  finished_at: number | null;
  attempts: number;
  run_after: number | null;
};

/** Một việc = một video đi qua chuỗi bước (tải → … → duyệt → đăng). */
export type Job = {
  id: number;
  flow: string;
  source: string;
  title: string;
  url: string | null;
  project_id: number | null;
  project_status: ProjectStatus | null;
  created_at: number;
  updated_at: number;
  state: "running" | "queued" | "retry" | "failed" | "review" | "done" | "stopped";
  summary: string;
  current: string;
  steps: JobStep[];
};

export type JobsResponse = { jobs: Job[]; active: number; now: number };

/** Một video quét từ link TikTok (PLAN-113). ``taken`` = đã có trong Studio / đang tải. */
export type TikTokItem = {
  id: string;
  url: string;
  title: string;
  views: number | null;
  duration: number | null;
  thumbnail: string | null;
  taken: boolean;
};

export type TakeBody = {
  items: { url: string; title: string }[];
  /** null = đăng tay (không qua Buffer) */
  channel_id: number | null;
  template_id: number | null;
  techniques: Techniques;
};

export type Voice = { name: string; gender: "female" | "male" | ""; region: string; description: string };
export type VoicesResponse = { online: boolean; voices: Voice[] };

export type Template = { id: number; name: string; kind: string; params: Record<string, unknown> };

export type SetupResponse = {
  channels: Channel[];
  buffer_channels: { id: string; name: string }[];
  templates: Template[];
  template_kinds: { kind: string; defaults: Record<string, unknown> }[];
  /** tên file .cube trong storage/media/luts */
  luts: string[];
};

/** PLAN-116 — ô tick kỹ thuật khi đưa video vào (gửi lên server dạng ``techniques``). */
export type Techniques = {
  subtitles: boolean;
  dub: boolean;
  vieneu_voice: string;
  hook: string;
  music_asset_id: number | null;
  mirror: boolean;
  lut: string;
};
