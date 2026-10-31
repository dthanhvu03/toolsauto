"""Empirical Adversarial Stress Harness for Cashback Hardened Components (Milestone 1 - Challenger 2).

Target Areas:
1. SQLite WAL Mode & Concurrency Stress:
   - Verify PRAGMA journal_mode, synchronous, busy_timeout on disk database initialized with TrackingRepository.connect().
   - Run concurrent write / read stress test across multiple threads to verify WAL mode allows concurrent reads without 'database is locked'.
   - Test concurrent writer contention handled cleanly by busy_timeout=15000.
2. Cache LRU Eviction & Bridge Failure Resilience:
   - Populate _CACHE with 600 items: verify exactly the oldest 20% (100 items) are evicted, keeping newer entries intact (no full flush).
   - Test LRU recency promotion (cache read refreshes seq/ts, sparing frequently accessed items from eviction).
   - Simulate bridge timeout / down conditions in fetch_shop_vouchers and verify poller event loop is not blocked longer than configured timeouts ((0.5, 0.8)).
   - Verify _check_sale_relay absorbs all exceptions to preserve poller loop liveness.
3. Subscriber Notification Queue & Native Newlines:
   - Verify enqueue_for_subscribers formats messages with html.escape and native \\n, with ZERO <br> tags in admin_notifications.message_html.
   - Verify double-unwrap behavior: an already wrapped an_redir link (https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fproduct%2F1%2F2&affiliate_id=123)
     is properly unwrapped so the resulting affiliate link is not double-nested.
   - Verify recursive multi-level unwrap and tracking parameter stripping on origin URLs.
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import tempfile
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from cashback_bot.db import TrackingRepository
from cashback_bot.poller import _check_sale_relay
from cashback_bot.sale_relay import (
    _clean_shopee_url,
    _unwrap,
    enqueue_for_subscribers,
    resolve_shopee_link,
)
from cashback_bot import shop_voucher as sv


# ==============================================================================
# TARGET AREA 1: SQLite WAL Mode & Concurrency Stress
# ==============================================================================

class TestSqliteWalConcurrency:
    @pytest.fixture
    def test_repo(self):
        tmpdir = tempfile.mkdtemp(prefix="test_wal_stress_")
        db_path = os.path.join(tmpdir, "tracking_test.sqlite3")
        repo = TrackingRepository(db_path)
        repo.migrate()
        yield repo, db_path
        # Cleanup
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_wal_pragmas_on_disk_database(self, test_repo):
        """Verify PRAGMA journal_mode, synchronous, busy_timeout on disk database."""
        repo, _ = test_repo
        with repo.connect() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]

            assert mode.lower() == "wal", f"Expected WAL mode, got {mode}"
            # SQLite returns 1 for NORMAL synchronous mode
            assert sync in (1, "NORMAL", "normal"), f"Expected synchronous NORMAL (1), got {sync}"
            assert busy >= 15000, f"Expected busy_timeout >= 15000, got {busy}"

    def test_concurrent_read_write_stress_no_database_locked(self, test_repo):
        """Stress test: 1 writer continuously committing while 10 concurrent readers

        execute 1,000 rapid read queries. In WAL mode, readers must never be blocked
        with 'database is locked'.
        """
        repo, _ = test_repo

        # Initialize base state
        with repo.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES ('stress_counter', '0')")
            conn.commit()

        stop_event = False
        reader_errors: list[Exception] = []
        reader_success_count = [0]
        writer_commits = [0]

        def writer_loop():
            nonlocal stop_event
            counter = 0
            while not stop_event:
                try:
                    with repo.connect() as conn:
                        counter += 1
                        conn.execute(
                            "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('stress_counter', ?)",
                            (str(counter),),
                        )
                        conn.commit()
                        writer_commits[0] = counter
                except Exception as exc:
                    stop_event = True
                    raise exc
                time.sleep(0.002)

        def reader_loop(reader_id: int, num_queries: int):
            for _ in range(num_queries):
                if stop_event:
                    break
                try:
                    with repo.connect() as conn:
                        row = conn.execute(
                            "SELECT value FROM bot_state WHERE key = 'stress_counter'"
                        ).fetchone()
                        val = int(row["value"]) if row else 0
                        assert val >= 0
                        reader_success_count[0] += 1
                except Exception as exc:
                    reader_errors.append(exc)
                    break
                time.sleep(0.001)

        # Launch 1 writer and 10 readers
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            writer_future = executor.submit(writer_loop)
            reader_futures = [executor.submit(reader_loop, i, 100) for i in range(10)]

            # Wait for all readers to finish
            for rf in reader_futures:
                rf.result()

            # Signal writer to stop
            stop_event = True
            writer_future.result()

        assert len(reader_errors) == 0, f"Readers encountered lock errors: {reader_errors}"
        assert reader_success_count[0] >= 1000, f"Expected 1000 successful reads, got {reader_success_count[0]}"
        assert writer_commits[0] > 0, "Writer executed zero commits"

    def test_concurrent_writer_contention_handled_by_busy_timeout(self, test_repo):
        """Stress test: 5 concurrent writers inserting unique event records.

        Validates that busy_timeout=15000 handles write lock serialization cleanly.
        """
        repo, _ = test_repo
        writer_errors: list[Exception] = []
        records_per_writer = 40

        def writer_task(writer_id: int):
            for i in range(records_per_writer):
                key = f"writer_{writer_id}_evt_{i}"
                try:
                    with repo.connect() as conn:
                        conn.execute(
                            """
                            INSERT INTO admin_notifications
                            (event_key, event_type, chat_id, message_html, created_at)
                            VALUES (?, 'TEST', ?, 'stress test msg', '2026-10-30T17:00:00Z')
                            """,
                            (key, 1000 + writer_id),
                        )
                        conn.commit()
                except Exception as exc:
                    writer_errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(writer_task, w) for w in range(5)]
            for f in futures:
                f.result()

        assert len(writer_errors) == 0, f"Writers encountered unhandled lock errors: {writer_errors}"

        # Verify all 200 records committed cleanly
        with repo.connect() as conn:
            count = conn.execute("SELECT count(*) FROM admin_notifications WHERE event_type = 'TEST'").fetchone()[0]
            assert count == 5 * records_per_writer, f"Expected 200 records, found {count}"


# ==============================================================================
# TARGET AREA 2: Cache LRU Eviction & Bridge Failure Resilience
# ==============================================================================

class TestCacheLruAndBridgeResilience:
    def setup_method(self):
        sv._CACHE.clear()
        sv._CACHE_SEQ = 0

    def teardown_method(self):
        sv._CACHE.clear()
        sv._CACHE_SEQ = 0

    def test_cache_population_600_items_evicts_oldest_20_percent_no_full_flush(self):
        """Populate _CACHE with 600 items.

        Capacity = 500.
        When reaching 500 items, the 501st insert triggers eviction of the oldest 20% (100 items).
        After all 600 items are inserted sequentially:
        - Exactly items 1..100 must be evicted.
        - Items 101..600 must be intact in the cache.
        - Final size must be 500 (400 retained + 100 new).
        - No full flush (cache clear) occurred.
        """
        for i in range(1, 601):
            sv._cache_set(str(i), [{"code": f"VOUCHER_{i}", "discount": i}])

        assert len(sv._CACHE) == 500, f"Expected cache size 500, got {len(sv._CACHE)}"

        # Check that the oldest 100 keys (1..100) were evicted
        evicted_keys = [str(i) for i in range(1, 101)]
        surviving_old_keys = [k for k in evicted_keys if k in sv._CACHE]
        assert len(surviving_old_keys) == 0, f"Oldest 100 items should be evicted, but found {surviving_old_keys}"

        # Check that newer 500 items (101..600) are all retained intact
        retained_keys = [str(i) for i in range(101, 601)]
        missing_retained_keys = [k for k in retained_keys if k not in sv._CACHE]
        assert len(missing_retained_keys) == 0, f"Newer entries should remain, missing: {missing_retained_keys[:10]}"

    def test_cache_lru_recency_promotion_prevents_eviction_of_read_keys(self):
        """LRU access recency: accessing an older item updates its (ts, seq)

        so that during the 20% eviction, the accessed item is preserved.
        """
        # Insert 500 items
        for i in range(1, 501):
            sv._cache_set(str(i), [{"code": f"VOUCHER_{i}"}])

        # Access item '10' and '20' (simulating cache hits)
        v10 = sv._cache_get("10")
        v20 = sv._cache_get("20")
        assert v10 is not None
        assert v20 is not None

        # Add item '501' -> triggers eviction of 100 oldest items
        sv._cache_set("501", [{"code": "VOUCHER_501"}])

        # '10' and '20' must NOT be evicted because their access was refreshed
        assert "10" in sv._CACHE, "Recently accessed item 10 was incorrectly evicted"
        assert "20" in sv._CACHE, "Recently accessed item 20 was incorrectly evicted"

        # An un-accessed early item (e.g. '1', '2') must have been evicted
        assert "1" not in sv._CACHE, "Unaccessed early item 1 should have been evicted"
        assert "2" not in sv._CACHE, "Unaccessed early item 2 should have been evicted"

    def test_bridge_timeout_resilience_bounds_delay_and_returns_fallback(self):
        """Simulate bridge timeout condition and verify:

        1. Configured timeout tuple is (0.5, 0.8)
        2. Execution does not block longer than timeout + small system jitter (< 2.5s)
        3. Returns (False, []) safely without raising unhandled exceptions.
        """
        assert sv.REQUEST_TIMEOUT_SEC == (0.5, 0.8), f"Expected (0.5, 0.8), got {sv.REQUEST_TIMEOUT_SEC}"

        def slow_get(*args, **kwargs):
            # Assert timeout tuple is passed to requests.get
            timeout = kwargs.get("timeout")
            assert timeout == (0.5, 0.8)
            time.sleep(0.9)  # Simulate hanging beyond read timeout
            raise requests.Timeout("Simulated bridge read timeout")

        start_time = time.monotonic()
        with patch("requests.get", side_effect=slow_get):
            ok, vouchers = sv.fetch_shop_vouchers("987654321")
        elapsed = time.monotonic() - start_time

        assert ok is False, "Expected False on bridge timeout"
        assert vouchers == [], "Expected empty vouchers on bridge timeout"
        # Since fallback URL may be tried if BRIDGE_URL != FALLBACK_BRIDGE_URL,
        # total time should not exceed 2 * (0.9s delay) + 0.5s margin = ~2.5s
        assert elapsed < 3.0, f"Bridge call took too long: {elapsed:.2f}s"

    def test_poller_check_sale_relay_catches_all_exceptions(self):
        """Verify poller's _check_sale_relay absorbs arbitrary exceptions

        from sale_relay.tick() so the main poller loop is never blocked or terminated.
        """
        mock_repo = MagicMock()
        mock_telegram = MagicMock()

        with patch("cashback_bot.sale_relay.tick", side_effect=RuntimeError("Bridge crashed / network down")):
            # Must not raise RuntimeError
            try:
                _check_sale_relay(mock_repo, mock_telegram, "12345")
            except Exception as exc:
                pytest.fail(f"_check_sale_relay leaked an exception: {exc}")


# ==============================================================================
# TARGET AREA 3: Subscriber Notification Queue & Native Newlines & Double-Unwrap
# ==============================================================================

class TestSubscriberQueueAndAffiliateUnwrap:
    @pytest.fixture
    def test_repo(self):
        tmpdir = tempfile.mkdtemp(prefix="test_sub_stress_")
        db_path = os.path.join(tmpdir, "tracking_test.sqlite3")
        repo = TrackingRepository(db_path)
        repo.migrate()
        yield repo, db_path
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_enqueue_for_subscribers_zero_br_tags_native_newlines_and_escaped(self, test_repo):
        """Empirically test that enqueue_for_subscribers:

        1. Preserves raw native newlines (\\n)
        2. Contains ZERO '<br>' or '<br/>' tags in admin_notifications.message_html
        3. Properly escapes HTML special characters (<, >, &)
        """
        repo, _ = test_repo
        post_id = 998877
        raw_message = (
            "🔥 DEAL HOT 50% OFF!\n"
            "Giá chỉ: 150.000₫ (giá gốc <300k>)\n"
            "Áp dụng cho đơn hàng Shopee & Zalo\n"
            "Link săn sale: https://s.shopee.vn/test123"
        )
        subscribers = [10001, 10002, 10003]
        buttons = [[{"text": "🛒 Mua ngay", "url": "https://s.shopee.vn/test123"}]]

        queued_count = enqueue_for_subscribers(repo, post_id, raw_message, buttons, subscribers)
        assert queued_count == 3, f"Expected 3 queued messages, got {queued_count}"

        with repo.connect() as conn:
            rows = conn.execute(
                "SELECT chat_id, message_html FROM admin_notifications WHERE event_key LIKE 'relay:998877:%'"
            ).fetchall()

            assert len(rows) == 3, f"Expected 3 rows in admin_notifications, got {len(rows)}"

            for row in rows:
                msg_html = row["message_html"]

                # 1. Zero <br> tags allowed
                assert "<br>" not in msg_html.lower(), f"Forbidden '<br>' tag found in message_html: {msg_html}"
                assert "<br/>" not in msg_html.lower(), f"Forbidden '<br/>' tag found in message_html: {msg_html}"
                assert "<br />" not in msg_html.lower(), f"Forbidden '<br />' tag found in message_html: {msg_html}"

                # 2. Native newlines preserved
                assert "\n" in msg_html, "Native newlines were not preserved in message_html"
                assert msg_html.count("\n") == 3, f"Expected 3 newlines, found {msg_html.count('\\n')}"

                # 3. HTML characters escaped
                assert "&lt;300k&gt;" in msg_html, f"Expected '&lt;300k&gt;', got: {msg_html}"
                assert "&amp; Zalo" in msg_html, f"Expected '&amp; Zalo', got: {msg_html}"
                assert "<300k>" not in msg_html, "Unescaped '<300k>' found in message_html"

    def test_double_unwrap_already_wrapped_an_redir_link(self):
        """Verify that an already wrapped an_redir link is unwrapped and clean:

        Input: https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fproduct%2F1%2F2&affiliate_id=123
        Result: unwrapped to https://shopee.vn/product/1/2
        Re-wrapped result origin_link must NOT contain 'an_redir'.
        """
        initial_wrapped = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fproduct%2F1%2F2&affiliate_id=123"

        # 1. Verify _unwrap extracts the true origin
        unwrapped = _unwrap(initial_wrapped)
        assert unwrapped == "https://shopee.vn/product/1/2", f"Failed to unwrap: got {unwrapped}"

        # 2. Verify _clean_shopee_url retains clean base
        cleaned = _clean_shopee_url(initial_wrapped)
        assert cleaned == "https://shopee.vn/product/1/2", f"Failed to clean unwrapped: got {cleaned}"

        # 3. Verify resolve_shopee_link wraps cleanly with our affiliate_id without double-nesting
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}

        with patch("cashback_bot.sale_relay.is_safe_shopee_url", return_value=True), \
             patch("cashback_bot.sale_relay._head", return_value=mock_resp):
            resolved = resolve_shopee_link(initial_wrapped, affiliate_id="999888")

        parsed = urlparse(resolved)
        assert parsed.scheme == "https"
        assert parsed.netloc == "s.shopee.vn"
        assert parsed.path == "/an_redir"

        q = parse_qs(parsed.query)
        assert q["affiliate_id"] == ["999888"]
        assert q["sub_id"] == ["AUTOSALE"]

        # The origin_link param MUST be the clean product URL, not another an_redir
        inner_origin = q["origin_link"][0]
        assert inner_origin == "https://shopee.vn/product/1/2", f"Double-nested an_redir detected in origin_link: {inner_origin}"
        assert "an_redir" not in inner_origin, f"'an_redir' still present in origin_link: {inner_origin}"

    def test_recursive_multi_level_unwrap_and_tracking_params_cleanup(self):
        """Stress-test triple-nested an_redir link with dirty tracking parameters:

        Level 1: s.shopee.vn/an_redir
        Level 2: shp.ee/an_redir
        Level 3: shopee.vn/product/777/888?utm_source=facebook&af_sub_siteid=999&smtt=0.0.9
        Must unwrap to https://shopee.vn/product/777/888 with all tracking params stripped.
        """
        inner_dirty = "https://shopee.vn/product/777/888?utm_source=facebook&af_sub_siteid=999&smtt=0.0.9"
        level2 = f"https://shp.ee/an_redir?origin_link={requests.utils.quote(inner_dirty)}&affiliate_id=444"
        level1 = f"https://s.shopee.vn/an_redir?origin_link={requests.utils.quote(level2)}&affiliate_id=333"

        unwrapped = _unwrap(level1)
        assert unwrapped == inner_dirty, f"Expected recursive unwrap to inner URL, got: {unwrapped}"

        cleaned = _clean_shopee_url(level1)
        assert cleaned == "https://shopee.vn/product/777/888", f"Expected stripped tracking params, got: {cleaned}"
        assert "utm_source" not in cleaned
        assert "af_sub_siteid" not in cleaned
        assert "smtt" not in cleaned
