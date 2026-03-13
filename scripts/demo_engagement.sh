#!/bin/bash
# ============================================================
# Demo 2 tính năng: Niche Topics UI + Idle Engagement
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   DEMO 1: Chỉnh sửa Niche Topics qua Dashboard API    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

echo "─── Bước 1: Xem niche hiện tại của 2 accounts ───"
cd /home/vu/toolsauto
./venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/auto_publisher.db')
cur = conn.cursor()
cur.execute('SELECT id, name, niche_topics FROM accounts')
for row in cur.fetchall():
    print(f'  📌 Account [{row[0]}] {row[1]}: {row[2]}')
conn.close()
"
echo ""

echo "─── Bước 2: Đổi niche cho 'Hoang Khoa' sang 'skincare, công nghệ, review đồ' qua API Save ───"
curl -s -X POST http://localhost:8000/accounts/3/update-limits \
  -d "daily_limit=3&cooldown_seconds=1800&niche_topics=skincare, công nghệ, review đồ" \
  > /dev/null
echo "  ✅ API POST /accounts/3/update-limits → 200 OK"
echo ""

echo "─── Bước 3: Kiểm tra lại giá trị sau khi Save ───"
./venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/auto_publisher.db')
cur = conn.cursor()
cur.execute('SELECT id, name, niche_topics FROM accounts')
for row in cur.fetchall():
    print(f'  📌 Account [{row[0]}] {row[1]}: {row[2]}')
conn.close()
"
echo ""

echo "─── Bước 4: Khôi phục về từ khóa gốc ───"
curl -s -X POST http://localhost:8000/accounts/3/update-limits \
  -d "daily_limit=3&cooldown_seconds=1800&niche_topics=mua sắm online, đồ gia dụng, deal giảm giá, review sản phẩm" \
  > /dev/null
echo "  ✅ Đã khôi phục account 'Hoang Khoa' về từ khóa gốc."
echo ""

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   DEMO 2: Idle Engagement Worker Live Log              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "─── Log Publisher Worker (các phiên Engagement gần nhất): ───"
echo ""
grep -E "\[IDLE\]|\[ENGAGEMENT\]" /home/vu/toolsauto/pub_worker.log | tail -20
echo ""

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   ✅ DEMO HOÀN TẤT                                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
