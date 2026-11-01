// Hình dạng dữ liệu server gửi (xe_tet/server/game/engine.py → snapshot() và outbox).

export type Phase = "BOARDING" | "DRIVING" | "REST" | "DROPOFF" | "FINISH" | "SPECIAL";
export type Region = "bac" | "trung" | "taynguyen" | "nam";

export type CamName = "wide" | "high" | "side" | "close";

// Thiết lập admin (xe_tet/server/settings.py)
export interface Control {
  view: "outside" | "inside";
  cam: CamName;
  zoom: number;
  fade?: boolean; // hiệu ứng chuyển cảnh mờ nhẹ (mặc định tắt: cắt thẳng)
  quality?: "high" | "low"; // chất lượng hình (thấp: máy yếu / LIVE Studio giật)
  auto_loxe?: boolean;
  show_route?: boolean;
  show_loxe?: boolean;
  show_toasts?: boolean;
  show_board?: boolean;
  board_seconds?: number;
  rest_seconds?: number;
  music_on?: boolean;  // nhạc trong xe (PLAN-127)
  music_volume?: number;
  sfx_volume?: number;
}

interface Lane { key: string; label: string; arrow: string; waiting: number; current: boolean }

/** Xe tăng cường chạy ngầm (PLAN-125). */
interface Relief { no: number; arrow: string; label: string; sponsor: string | null; riders: number; next: string;
  left_km: number; featured: boolean }

/** Người đang chờ xe sau (hiện tên + thứ tự trên màn hình), làn chạy kế tiếp trước. */
interface Waiting { name: string; hue: number; province: string; arrow: string; pos: number }

export interface Seat {
  name: string;
  hue: number;
  vip: boolean;
  province: string;
}

export interface State {
  phase: Phase;
  paused: boolean;
  control?: Control;
  sim_rate?: number;
  phase_left: number | null;
  phase_total: number | null;  // độ dài pha hiện tại (thanh tiến độ trạm nghỉ, kể cả khi cao điểm rút ngắn)
  bus: {
    no: number; seats: (Seat | null)[]; banner: string | null; riders: number;
    lane: string; arrow: string; to: string; km: number | null;  // làn, tỉnh đặt tên làn, km xe chạy cả chuyến
  };
  departure: { key: string; name: string; short: string };
  lanes: Lane[];
  trip_km: number;  // km xe đã chạy từ bến
  // độ quanh co (độ / km) + đèo / hầm đang qua; climb: +1 đang leo đèo, −1 đang đổ đèo, 0 đường thường / hầm
  terrain: { wind: number; pass: string | null; tunnel: boolean; climb: number };
  waiting: number;
  reliefs: Relief[];
  featured: number | null;
  music: { index: number; on: boolean };  // đài của xe đang chiếu: bài thứ index (vòng) trong music_tracks
  music_tracks?: { id: string; title: string; url?: string }[];  // xe tăng cường admin đang chiếu (các trường bus / legs / terrain… là của xe đó)
  next_lane: { label: string; arrow: string; bus_no: number; eta_min: number } | null;
  queue: Waiting[];
  legs: { kind: "rest" | "stop"; label: string; km: number }[];
  leg_index: number;
  progress: number;
  speed: number;
  leg_seconds: number;
  region: Region;
  place: string;  // tỉnh xe đang ở / đi qua
  specialty: string;
  rest: { orders: { item: string; emoji: string; count: number }[]; wc_count: number };
  staying: string[];
  staying_count: number;
  board: { province: string; count: number }[];
  trip_likes: number;
  delivered: number;
  days_to_tet: number;
  rush?: boolean; // giờ cao điểm: hàng chờ ≥ 1 xe, chuyến tự ngắn lại
}

interface Person {
  name: string;
  hue: number;
  vip: boolean;
  wish: string;
}

// Sự kiện rời rạc; mỗi loại chỉ dùng vài trường.
export interface GameEvent {
  type: string;
  name?: string;
  names?: string[];
  count?: number;
  hue?: number;
  text?: string;
  seat?: number | null;
  province?: string | null;
  bus_no?: number;
  next?: boolean;
  changed?: boolean;
  tier?: number;
  tier_up?: boolean; // quà: vừa lên bậc mới (cộng dồn trong chuyến)
  perk?: string;
  action?: string; // rest_action: food | wc | shop
  emoji?: string;
  people?: Person[];
  fireworks?: boolean;
  region?: Region;
  specialty?: string;
  place?: string;  // trạm dừng chân: tỉnh có trạm
  total?: number;
  board?: { province: string; count: number }[];
  top_liker?: string | null;
  delivered?: number;
  title?: string;
  seconds?: number;
  page_size?: number;
  page_seconds?: number;
  lane?: string;  // vé / xuất bến: «Hướng Hà Nội»
  arrow?: string;
  km?: number;  // km thật từ bến đi
  hours?: number;  // giờ xe khách thật (thả khách)
  departure?: string;  // tên ngắn bến đi: «TP.HCM»
  delivered_km?: number;
  sponsor?: string | null;  // xe tăng cường do ai tặng quà gọi
  eta_min?: number; // vé xe sau: ước số phút tới lúc được lên xe
  next_tier?: string; // quà: «thêm X xu → …»
  diamonds?: number; // quà: xu của lần tặng này (total = cộng dồn trong chuyến)
}
