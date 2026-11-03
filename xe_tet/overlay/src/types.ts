// Hình dạng dữ liệu server gửi (xe_tet/server/game/engine.py → snapshot() và outbox).

export type Phase = "BOARDING" | "DRIVING" | "REST" | "DROPOFF" | "FINISH" | "SPECIAL";
export type Region = "bac" | "trung" | "taynguyen" | "nam";

export type CamName = "wide" | "high" | "side" | "close";
export type Quality = "high" | "medium" | "low";

// Thiết lập admin (xe_tet/server/settings.py)
export interface Control {
  view: "outside" | "inside";
  cam: CamName;
  zoom: number;
  fade?: boolean; // hiệu ứng chuyển cảnh mờ nhẹ (mặc định tắt: cắt thẳng)
  quality?: Quality; // chất lượng hình (vừa: khuyên dùng khi live; thấp: máy yếu)
  auto_loxe?: boolean;
  show_route?: boolean;
  show_loxe?: boolean;
  show_toasts?: boolean;
  show_board?: boolean;
  board_seconds?: number;
  rest_seconds?: number;
  music_on?: boolean;  // nhạc trong xe (PLAN-127)
  music_auto?: boolean;  // hết bài tự qua bài (server đổi bài, overlay chỉ phát)
  music_volume?: number;
  sfx_volume?: number;
  voice_on?: boolean;
  show_sound?: boolean;  // bảng quảng cáo: phát tiếng video  // giọng Anh Tư lơ xe (PLAN-128)
  voice_volume?: number;
  voice_rate?: number;  // tốc độ đọc 0,8 – 1,6
  trip_minutes?: number;  // chuyến xa nhất chạy bao nhiêu phút (PLAN-130)
  auto_feature?: "off" | "events" | "rotate";
  rotate_seconds?: number;
  mix?: "balanced" | "music" | "voice";  // trộn tiếng
  hud_scale?: number;  // cỡ chữ trên live 0,6 – 1,2 (PLAN-133)
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
  avatar?: string;  // ảnh đại diện TikTok
  snack?: string;  // món mua của cô bán hàng (emoji) — hiện cạnh tên
}

export interface Vendor {  // cô bán hàng lên xe (anh 03/11): góp quà → tấp vào lề cho cô lên → bán trong lúc xe chạy
  stage: "pool" | "stop" | "sell";
  name: string;
  paid?: number; goal?: number;  // pool
  left?: number; by?: string; sold?: number; treats?: string[];
}

export interface State {
  phase: Phase;
  paused: boolean;
  control?: Control;
  sim_rate?: number;
  phase_left: number | null;
  phase_total: number | null;  // độ dài pha hiện tại (thanh tiến độ trạm nghỉ, kể cả khi cao điểm rút ngắn)
  bus: {
    no: number; seats: (Seat | null)[]; banner: string | null; riders: number; parcels?: number;
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
  // đài của xe đang chiếu: bài thứ index (vòng) trong music_tracks, bắt đầu lúc since, đã phát được pos giây
  music: { index: number; on: boolean; since: number; pos: number };
  music_tracks?: { id: string; title: string; url?: string; seconds: number }[];  // xe tăng cường admin đang chiếu (các trường bus / legs / terrain… là của xe đó)
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
  season?: { phase: string; lunar: string | null; days_to_tet: number };  // lịch mùa Tết (PLAN-134 C)
  stations?: { key: string; name: string; votes: number; need: number }[];  // bến người xem đang gọi (PLAN-136)
  care?: { fuel: number; dirt: number; bonus: number };  // xăng / độ bẩn (PLAN-137)
  audio_screen?: number | null;  // số màn hình game được phát tiếng (các màn khác im)
  rush?: boolean; // giờ cao điểm: hàng chờ ≥ 1 xe, chuyến tự ngắn lại
  route?: Route;  // bảng chặng của xe đang chiếu (PLAN-130)
  fleet?: FleetBus[];  // mọi xe đang chạy
  trip_minutes?: number;
  patrons?: { name: string; xu: number }[];  // Chủ nhà xe, Phó nhà xe (PLAN-144)
  vendor?: Vendor | null;
  name_hold?: boolean;  // hết giờ đón, xe chờ lơ xe đọc xong tên người lên xe
  rollcall?: { name: string; left: number }[];  // điểm danh: người tới lượt lên xe đang được gọi tên (anh 03/11)
  halt?: { place: string; people: { name: string; hue: number; province: string }[]; left: number } | null;  // dừng đón bên đường (PLAN-145)
  turbo?: { left: number; by: string } | null;  // quà: xe chạy x2 còn bao nhiêu giây, ai tặng gần nhất
  block?: Block | null;
  focus?: { seat: number; name: string; vip: boolean; province: string; stops_before: number | null; in_s: number | null; trips: number; left: number } | null;
  show?: { url: string; title: string; seconds: number; left: number } | null;  // đang dừng xem video bảng quảng cáo
  race?: { province: string; points: number }[];  // đua tỉnh vòng này
  videos?: { name: string; title: string; url: string; seconds: number }[];
  goal?: { xu: number; goal: number; round: number; next_xu: number; next: string };  // mục tiêu buổi live  // trạm thu phí / công an chặn xe, chờ góp quà (PLAN-148)
}

/** Đồng hồ trên xe: giờ VN lúc xuất bến + giờ xe chạy (giờ trong ngày, «HH:MM», ngày thứ mấy từ hôm xuất bến). */
export interface BusClock { hour: number; time: string; day: number }

export interface Route {
  stops: { kind: "rest" | "stop"; name: string; km: number; done: boolean; in_s: number | null; at: string | null;
    day: number | null }[];
  via?: { name: string; km: number; done: boolean }[];  // tỉnh xe đi qua mà không ai xuống (PLAN-134)
  odo: number;
  total: number;
  clock: BusClock;
}

export interface FleetBus {
  no: number; main: boolean; featured: boolean; arrow: string; label: string; phase: Phase; riders: number;
  left_km: number | null; next: string | null; in_s: number | null; clock: BusClock | null; sponsor?: string | null;
  stops: Route["stops"];
}

interface Person {
  name: string;
  hue: number;
  vip: boolean;
  wish: string;
  parcels?: number;  // thùng quà Tết ôm vào cổng (PLAN-134 C)
}

/** Xe đang bị chặn: góp quà đủ `goal` xu thì đi tiếp. */
export interface Block {
  kind: "toll" | "police";
  reason: string;
  goal: number;
  paid: number;
  place: string;
  speeding: boolean;
  top: { name: string; xu: number }[];
  waited: number;
  cover_in: number | null;
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
  item?: string;  // snack / vendor_treat
  avatar?: string;  // ảnh đại diện TikTok của người trong sự kiện
  stage?: string;  // vendor: stop | sell
  riders?: number;  // vendor_treat: số người trên xe được bao
  sold?: number;  // vendor_end
  people?: Person[];
  fireworks?: boolean;
  region?: Region;
  specialty?: string;
  place?: string;  // trạm dừng chân: tỉnh có trạm
  label?: string; round?: number;  // goal_step
  points?: number;  // race_win
  kind?: string; reason?: string; goal?: number; paid?: number; by?: string; speeding?: boolean;  // block / block_end
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
  fx?: string;  // quà: hiệu ứng riêng của món (petals | honk | hearts | firework | lixi | lantern — PLAN-142)
  fx_n?: number;
  xu?: number;  // patron (PLAN-144)
  promoted?: boolean;  // vé: người đang giữ chỗ vừa được xếp lên xe
  relief?: boolean;  // vé: lên xe tăng cường
  url?: string;  // speak: file giọng lơ xe đọc sẵn
  eta_min?: number; // vé xe sau: ước số phút tới lúc được lên xe
  // tra vé «xe nào / tới đâu rồi» (PLAN-134 B)
  status?: "seat" | "relief" | "queue" | "home" | "none";
  parcel?: boolean;  // quà vừa tặng thành thùng quà trên gầm xe (PLAN-134 C)
  pickup?: string;  // bắt xe dọc đường (PLAN-136): tỉnh có điểm đón
  pickup_in?: number;  // giây tới lúc xe tới điểm đón
  passed?: string;  // xe đã qua quê người này → giữ chỗ xe sau
  station?: string;  // gọi xe ra bến khác (PLAN-136)
  votes?: number;
  need?: number;
  trip_no?: number;  // chuyến thứ mấy của người này
  level?: number;  // đổ xăng / rửa xe: mức sau khi làm (0 → 1)
  trips?: number;  // khách quay lại: số chuyến đã về quê (PLAN-134 D)
  home?: string | null;
  days?: number;
  phase?: string;
  in_s?: number | null;
  stops_before?: number;
  depart_in?: number | null;
  position?: number;
  next_tier?: string; // quà: «thêm X xu → …»
  diamonds?: number; // quà: xu của lần tặng này (total = cộng dồn trong chuyến)
}
