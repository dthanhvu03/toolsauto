"""Toạ độ để tính tuyến thật (BRD-tuyen-xe.md): tỉnh lỵ 63 tỉnh, bến đi admin chọn, các đèo nổi tiếng.

Toạ độ lấy gần đúng trung tâm tỉnh lỵ / bến xe — đủ cho định tuyến đường bộ (sai lệch vài km), không dùng để dẫn đường.
Chỉ `tools/build_routes.py` (chạy một lần, có mạng) và bảng dữ liệu sinh ra dùng tới; game không gọi mạng.
"""

from dataclasses import dataclass

# (vĩ độ, kinh độ) trung tâm tỉnh lỵ — vĩ độ khớp provinces.py
CAPITALS: dict[str, tuple[float, float]] = {
    "hanoi": (21.03, 105.85), "haiphong": (20.86, 106.68), "quangninh": (20.95, 107.08), "haiduong": (20.94, 106.33),
    "hungyen": (20.65, 106.05), "thaibinh": (20.45, 106.34), "namdinh": (20.42, 106.17), "hanam": (20.54, 105.92),
    "ninhbinh": (20.25, 105.97), "bacninh": (21.19, 106.08), "bacgiang": (21.27, 106.20), "vinhphuc": (21.31, 105.60),
    "phutho": (21.32, 105.40), "thainguyen": (21.59, 105.84), "hoabinh": (20.82, 105.34), "sonla": (21.33, 103.91),
    "dienbien": (21.39, 103.02), "laichau": (22.40, 103.46), "laocai": (22.48, 103.97), "yenbai": (21.72, 104.87),
    "tuyenquang": (21.82, 105.21), "hagiang": (22.82, 104.98), "caobang": (22.67, 106.25), "backan": (22.15, 105.83),
    "langson": (21.85, 106.76),
    "thanhhoa": (19.81, 105.78), "nghean": (18.68, 105.69), "hatinh": (18.34, 105.90), "quangbinh": (17.47, 106.62),
    "quangtri": (16.75, 107.10), "hue": (16.46, 107.59), "danang": (16.05, 108.20), "quangnam": (15.57, 108.47),
    "quangngai": (15.12, 108.80), "binhdinh": (13.78, 109.22), "phuyen": (13.09, 109.30), "khanhhoa": (12.24, 109.19),
    "ninhthuan": (11.56, 108.99), "binhthuan": (10.93, 108.10),
    "kontum": (14.35, 108.00), "gialai": (13.98, 108.00), "daklak": (12.67, 108.04), "daknong": (12.00, 107.69),
    "lamdong": (11.94, 108.44),
    "hcm": (10.78, 106.70), "dongnai": (10.95, 106.82), "binhduong": (10.98, 106.65), "binhphuoc": (11.54, 106.90),
    "tayninh": (11.31, 106.10), "bariavungtau": (10.40, 107.17), "longan": (10.54, 106.41), "tiengiang": (10.36, 106.36),
    "bentre": (10.24, 106.38), "vinhlong": (10.25, 105.97), "travinh": (9.93, 106.34), "dongthap": (10.46, 105.63),
    "angiang": (10.39, 105.43), "kiengiang": (10.01, 105.08), "cantho": (10.03, 105.78), "haugiang": (9.78, 105.47),
    "soctrang": (9.60, 105.97), "baclieu": (9.29, 105.72), "camau": (9.18, 105.15),
}


@dataclass(frozen=True)
class Departure:
    key: str
    name: str
    short: str  # tên ngắn hiện trên bảng LED / vé: «TP.HCM → HÀ NỘI»
    province: str  # tỉnh của bến — khách comment tỉnh này thì «đã ở quê» (BR-5)
    lat: float
    lon: float


# Bến đi admin chọn (BR-8). Mặc định Miền Đông mới (anh duyệt 31/10).
DEPARTURES: tuple[Departure, ...] = (
    Departure("hcm_miendong", "Bến xe Miền Đông mới", "TP.HCM", "hcm", 10.8786, 106.8147),
    Departure("hn_giapbat", "Bến xe Giáp Bát", "Hà Nội", "hanoi", 20.9806, 105.8413),
    Departure("dalat", "Bến xe Liên tỉnh Đà Lạt", "Đà Lạt", "lamdong", 11.9286, 108.4458),
    Departure("danang", "Bến xe Trung tâm Đà Nẵng", "Đà Nẵng", "danang", 16.0596, 108.1752),
    Departure("cantho", "Bến xe Trung tâm Cần Thơ", "Cần Thơ", "cantho", 10.0124, 105.7516),
)
DEFAULT_DEPARTURE = "hcm_miendong"

# Đèo nổi tiếng (toạ độ gần đúng giữa đèo): lộ trình đi qua trong vòng ~4 km thì đoạn đó là «đèo» — dốc + cua gắt.
PASSES: tuple[tuple[str, float, float], ...] = (
    ("Đèo Hải Vân", 16.197, 108.130), ("Đèo Ngang", 17.958, 106.466), ("Đèo Cả", 12.890, 109.399),
    ("Đèo Cù Mông", 13.605, 109.208), ("Đèo Prenn", 11.880, 108.460), ("Đèo Bảo Lộc", 11.430, 107.730),
    ("Đèo Ngoạn Mục", 11.805, 108.655), ("Đèo Khánh Lê", 12.255, 108.705), ("Đèo Mimosa", 11.905, 108.430),
    ("Đèo Lò Xo", 15.170, 107.720), ("Đèo Mang Yang", 13.960, 108.290), ("Đèo Phượng Hoàng", 12.620, 108.660),
    ("Đèo Tam Điệp", 20.160, 105.930), ("Đèo Thung Khe", 20.690, 105.140), ("Đèo Pha Đin", 21.570, 103.510),
    ("Đèo Ô Quy Hồ", 22.350, 103.770), ("Đèo Mã Pí Lèng", 23.230, 105.410), ("Đèo Khau Phạ", 21.770, 104.250),
    ("Đèo Sài Hồ", 21.680, 106.640), ("Đèo Cổ Mã", 12.790, 109.330),
)

# Đèo đã có hầm xuyên núi (QL1 / cao tốc Bắc – Nam). Lộ trình qua đó mà thẳng (đo được) là đi hầm, không leo đèo.
# Nguồn: Hải Vân 2005 (+ Hải Vân 2 2021), Đèo Cả + Cổ Mã 2017, Cù Mông 2019, Tam Điệp (cao tốc Mai Sơn – QL45, 2023);
# hầm Đèo Ngang (2018) có nhưng dữ liệu bản đồ vẫn dẫn xe qua đỉnh đèo → giữ là đèo theo dữ liệu.
TUNNELS: dict[str, str] = {
    "Đèo Hải Vân": "Hầm Hải Vân", "Đèo Cả": "Hầm Đèo Cả", "Đèo Cổ Mã": "Hầm Cổ Mã", "Đèo Cù Mông": "Hầm Cù Mông",
    "Đèo Ngang": "Hầm Đèo Ngang", "Đèo Tam Điệp": "Hầm Tam Điệp",
}

# Điểm trên Quốc lộ 1 để dẫn lại tuyến bị OSRM vòng qua Lào / Campuchia (tools/build_routes.py).
QL1_VIAS: tuple[tuple[str, float, float], ...] = (
    ("Cam Ranh", 11.92, 109.15), ("Quảng Ngãi", 15.12, 108.80), ("Đông Hà", 16.82, 107.10), ("Vinh", 18.68, 105.68),
)
