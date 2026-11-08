import type { SettingsFieldMeta } from "../types/settings.types";

/**
 * Cài đặt theo màn hình: mỗi màn hình khai báo section nào (id từ `/api/settings/metadata`) và chia nhóm ra sao.
 * Nút ⚙️ (`ScreenSettingsButton`) mở modal chỉ chứa đúng những ô này — lưu xong là có hiệu lực (backend đọc DB, cache 3s),
 * trừ ô có nhãn «restart». Trang «Cài đặt» vẫn giữ đầy đủ mọi section.
 *
 * `keys` của nhóm: khoá chính xác hoặc tiền tố kết thúc bằng `*`. Ô không thuộc nhóm nào → nhóm theo tên section.
 */
export type ScreenGroup = { title: string; keys: string[] };

export type ScreenSettingsConfig = {
  title: string;
  sections: string[];
  groups?: ScreenGroup[];
};

export const SCREEN_SETTINGS = {
  "studio-doc": {
    title: "Cài đặt Audio→Doc",
    sections: ["studio_audio_doc"],
    groups: [
      {
        title: "Chia cảnh theo lời",
        keys: ["doc.default_language", "doc.shot_sec", "doc.shot_min_sec", "doc.shot_max_sec", "doc.beat_*"],
      },
      {
        title: "Nguồn ảnh",
        keys: [
          "doc.src_wikimedia", "doc.src_openverse", "doc.src_pexels", "doc.pexels_key", "doc.src_pixabay",
          "doc.pixabay_key", "doc.src_google", "doc.google_key", "doc.google_cx", "doc.ai_keywords",
          "doc.candidates_per_source", "doc.search_timeout_sec", "doc.image_*",
        ],
      },
      { title: "Bản quyền ảnh", keys: ["doc.rights_*", "doc.auto_verify_licenses", "doc.credit"] },
      { title: "Khung hình & chuyển động", keys: ["doc.canvas", "doc.fps", "doc.fit", "doc.motions", "doc.kb_*"] },
      { title: "Phụ đề, âm thanh, xem thử", keys: ["doc.subtitle*", "doc.voice_volume", "doc.preview_sec"] },
    ],
  },
  "threads-growth": {
    title: "Cài đặt Kéo khách",
    sections: ["threads_keo_khach"],
    groups: [
      {
        title: "Bật / tắt & lịch quét",
        keys: ["growth.enabled", "growth.scan_interval_min", "growth.posts_per_keyword", "growth.telegram_review"],
      },
      {
        title: "Hạn mức & ngưỡng điểm",
        keys: [
          "growth.max_replies_per_hour", "growth.max_replies_per_day", "growth.min_delay_sec", "growth.max_delay_sec",
          "growth.auto_post_min_relevance", "growth.min_relevance",
        ],
      },
      {
        title: "Lọc bài",
        keys: [
          "growth.search_top", "growth.min_reach", "growth.max_post_age_hours", "growth.author_cooldown_days",
          "growth.vietnamese_only", "growth.top_level_only",
        ],
      },
      { title: "Từ khóa tìm bài", keys: ["growth.keywords_*"] },
      { title: "Bài riêng trên tài khoản", keys: ["growth.own_posts_enabled", "growth.own_post_times"] },
      {
        title: "Trả lời người hỏi lại",
        keys: ["growth.followup_enabled", "growth.followup_max_per_day", "growth.followup_lookback_hours"],
      },
      { title: "Câu mẫu Cashbot (A/B)", keys: ["growth.cashbot_*"] },
      { title: "Câu mẫu AI Pass Store (A/B)", keys: ["growth.ai_store_*"] },
    ],
  },
  viral: { title: "Cài đặt quét & reup", sections: ["quet_tiktok_and_viral", "reup_lop_them"] },
  "viral-sources": { title: "Cài đặt quét nguồn", sections: ["quet_tiktok_and_viral"] },
  jobs: {
    title: "Cài đặt đăng bài",
    sections: ["gioi_han_dang_bai", "publisher_and_playwright", "tuong_tac_khi_ranh"],
  },
  studio: { title: "Cài đặt dựng video", sections: ["xu_ly_video_ffmpeg", "bao_ve_video_drm"] },
  "ai-studio": { title: "Cài đặt AI", sections: ["ai_and_whisper", "ai_keys"] },
  overview: { title: "Cài đặt tích hợp", sections: ["tich_hop"] },
  syspanel: {
    title: "Cài đặt hệ thống",
    sections: [
      "bat_tat_tinh_nang", "he_thong_worker", "bao_tri_and_canh_bao", "giam_sat", "sao_luu_google_drive",
      "he_thong_and_lien_ket",
    ],
  },
} satisfies Record<string, ScreenSettingsConfig>;

export type ScreenId = keyof typeof SCREEN_SETTINGS;

function matches(key: string, pattern: string): boolean {
  return pattern.endsWith("*") ? key.startsWith(pattern.slice(0, -1)) : key === pattern;
}

/** Chia các ô của màn hình thành nhóm theo thứ tự khai báo; ô dư → nhóm theo section. */
export function groupScreenFields(
  schema: SettingsFieldMeta[],
  cfg: ScreenSettingsConfig
): { title: string; fields: SettingsFieldMeta[] }[] {
  const pool = schema.filter((f) => cfg.sections.includes(f.section));
  const used = new Set<string>();
  const out: { title: string; fields: SettingsFieldMeta[] }[] = [];
  for (const g of cfg.groups ?? []) {
    const fields: SettingsFieldMeta[] = [];
    for (const pat of g.keys) {
      for (const f of pool) {
        if (!used.has(f.key) && matches(f.key, pat)) {
          used.add(f.key);
          fields.push(f);
        }
      }
    }
    if (fields.length) out.push({ title: g.title, fields });
  }
  for (const sid of cfg.sections) {
    const rest = pool.filter((f) => f.section === sid && !used.has(f.key));
    if (!rest.length) continue;
    const label = rest[0].sectionLabel || sid;
    out.push({ title: cfg.groups?.length ? `Khác — ${label}` : label, fields: rest });
  }
  return out;
}
