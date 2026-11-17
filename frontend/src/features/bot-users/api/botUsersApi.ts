import { getJson } from "@/shared/api/http";

export type BotKey = "cashbot_tg" | "cashbot_zalo" | "ai_store";

export type BotSummary = {
  bot: BotKey | "all";
  label: string;
  total: number;
  new_24h: number;
  new_7d: number;
  active_7d: number;
  buyers: number;
  available?: boolean;
};

export type Person = {
  bot: BotKey;
  user_id: number;
  name: string;
  joined_at: string | null;
  last_seen_at: string | null;
  last_used_at: string | null;
  source: string;
  uses: number;
  orders: number;
  active: boolean;
  balance: number | null;
  spent: number | null;
};

export type BotUsersReport = {
  generated_at: string;
  active_days: number;
  bots: BotSummary[];
  total: BotSummary;
  days: ({ day: string } & Record<BotKey, number>)[];
  sources: Record<BotKey, { source: string; count: number }[]>;
  matched: number;
  page: number;
  per_page: number;
  total_pages: number;
  people: Person[];
  errors: string[];
};

export const fetchBotUsers = (q: string, bot: string, page = 1, perPage = 25, summaryOnly = false) =>
  getJson<BotUsersReport>(`/bot-users/api/report?q=${encodeURIComponent(q)}&bot=${encodeURIComponent(bot)}&page=${page}&per_page=${perPage}&summary_only=${summaryOnly}`);
