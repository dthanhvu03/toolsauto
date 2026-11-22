"""Periodic growth review uses temporary databases and mocked model outputs only."""

import fcntl
import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.features.threads.growth import strategy_review as review

NOW = datetime(2026, 11, 19, 15, tzinfo=timezone.utc)
JOINED = (NOW - timedelta(hours=30)).isoformat()
EVENT = (NOW - timedelta(hours=2)).isoformat()
RESEARCH = {"experiments": [{"lane": "buyer", "hypothesis": "Làm rõ thời gian cần dùng CapCut trước giới thiệu gói",
                            "evidence": "Cohort7d còn nhỏ, không suy nguyên nhân", "kpi": "2 khách mới dùng thật",
                            "stop_rule": "Rà sau48h trong quota hiện tại"},
                           {"lane": "help_first", "hypothesis": "Hỏi phiên bản CapCut khi người dùng báo lỗi xuất video",
                            "evidence": "Chưa có nhãn nhu cầu lỗi cụ thể", "kpi": "5 hội thoại được trả lời",
                            "stop_rule": "Rà sau48h, không link/chào bán"}]}
CONTENT = {"drafts": [{"audience": "Người hỏi CapCut", "need": "Chọn gói phù hợp",
                       "draft": "Bạn cần dùng CapCut trong bao lâu, và đang dùng điện thoại hay máy tính?",
                       "cta": "Xem mô tả hiện tại trong bot", "verify": "Kiểm mô tả sản phẩm trước gửi"},
                      {"audience": "Người săn mã", "need": "Hiểu số hoàn dự kiến",
                       "draft": "Mở món trên Shopee → Chia sẻ → Sao chép liên kết, rồi dán link sản phẩm vào bot để xem hoàn dự kiến.",
                       "cta": "Tham khảo cách dùng bot", "verify": "Kiểm điều kiện hoàn hiện tại"}]}


@pytest.fixture
def environment(tmp_path):
    growth, cashback, store = (tmp_path / f"{name}.sqlite" for name in ("growth", "cashback", "store"))
    with sqlite3.connect(cashback) as conn:
        conn.executescript("""
            CREATE TABLE telegram_users(telegram_user_id INTEGER,created_at TEXT);
            CREATE TABLE bot_state(key TEXT,value TEXT);
            CREATE TABLE link_requests(id INTEGER,telegram_user_id INTEGER,sub_id TEXT,link_status TEXT,created_at TEXT);
            CREATE TABLE shopee_clicks(click_id TEXT,sub_id TEXT,click_time TEXT);
            CREATE TABLE shopee_conversions(conversion_id TEXT,order_sn TEXT,telegram_user_id INTEGER,
                order_status TEXT,validation_status TEXT,fraud_flag INTEGER,purchase_time TEXT);
        """)
        conn.executemany("INSERT INTO telegram_users VALUES(?,?)", [(101, JOINED), (777777777, JOINED)])
        conn.executemany("INSERT INTO bot_state VALUES(?,?)", [("src:101", "threads_cb_save"),
                                                               ("src:777777777", "private@source.invalid")])
        conn.executemany("INSERT INTO link_requests VALUES(?,?,?,'created',?)",
                         [(1, 101, "a", EVENT), (2, 777777777, "b", EVENT)])
    with sqlite3.connect(store) as conn:
        conn.executescript("""
            CREATE TABLE users(user_id INTEGER,created_at TEXT);
            CREATE TABLE state(key TEXT,value TEXT);
            CREATE TABLE topups(id INTEGER,user_id INTEGER,created_at TEXT,resolved_at TEXT,intent_product_id INTEGER,status TEXT);
            CREATE TABLE orders(id INTEGER,user_id INTEGER,created_at TEXT,status TEXT,total INTEGER,refunded INTEGER);
        """)
        conn.executemany("INSERT INTO users VALUES(?,?)", [(102, JOINED), (888888888, JOINED)])
        conn.executemany("INSERT INTO state VALUES(?,?)", [("src:102", "private@source.invalid"),
                                                          ("src:888888888", "threads_ai_price")])
        conn.executemany("INSERT INTO orders VALUES(?,?,?,'done',34000,0)",
                         [(1, 102, EVENT), (2, 888888888, EVENT)])
    with sqlite3.connect(growth) as conn:
        conn.executescript("""
            CREATE TABLE growth_posts(id INTEGER,target_bot TEXT,status TEXT,content TEXT,suggested_reply TEXT,
                actual_reply TEXT,post_created_at TEXT,posted_at TEXT);
            CREATE TABLE followups(status TEXT,created_at TEXT,growth_post_id INTEGER,author TEXT);
            CREATE TABLE dm_messages(thread_id TEXT,account TEXT,direction TEXT,created_at TEXT);
        """)
        conn.execute("INSERT INTO growth_posts VALUES(1,'cashbot','posted','Xin mã giảm giá Shopee',"
                     "'Bạn xem trong bot',NULL,?,?)", (EVENT, EVENT))
        conn.execute("INSERT INTO growth_posts VALUES(2,'ai_store','approved','Tuyển editor biết CapCut',"
                     "'Bạn xem trong bot',NULL,?,NULL)", (EVENT,))
        conn.execute("INSERT INTO followups VALUES('answered',?,1,'secret-author')", (EVENT,))
        conn.executemany("INSERT INTO dm_messages VALUES('secret-thread','secret-handle',?,?)",
                         [("in", EVENT), ("out", EVENT)])
    calls = []

    def generator(prompt, **_kwargs):
        calls.append(prompt)
        return json.dumps(CONTENT if '"drafts"' in prompt else RESEARCH, ensure_ascii=False), {"ok": True}

    args = {"generator": generator, "growth_path": growth, "cashback_path": cashback, "store_path": store,
            "state_path": tmp_path / "state.json", "output_dir": tmp_path / "reviews",
            "exclusions": {"cashbot": (777777777,), "ai_store": (888888888,)}}
    return args, calls


def artifact(args):
    return json.loads((args["output_dir"] / "latest.json").read_text())


def test_sql_scorecard_exclusions_and_private_values_never_exported(environment):
    args, calls = environment
    paths = [args[k] for k in ("growth_path", "cashback_path", "store_path")]
    before = [p.read_bytes() for p in paths]
    assert review.review_due(NOW, **args)["status"] == "completed"
    output = artifact(args)
    assert len(calls) == 2
    assert [p.read_bytes() for p in paths] == before
    evidence = output["evidence"]
    grouped = {(r["bot"], r["source_group"]): r for r in evidence["windows"]["7d"]["business"]["groups"]}
    assert grouped[("cashbot_tg", "threads")]["used_customers"] == 1
    assert grouped[("ai_store", "other")]["delivered_order_customers"] == 1
    assert all(r["customers"] == 1 for r in grouped.values())
    activity = evidence["windows"]["24h"]["activity"]
    assert activity["public_replies_sent"] == {"cashbot": 1, "ai_store": 0}
    assert activity["current_held_queue_rows_unique"] == 1
    assert activity["dm_inbound_threads_answered"] == 1
    assert activity["public_answered_conversations"] == 1
    assert activity["answered_two_way_conversations"] == 2
    assert activity["qualified_two_way_conversations"] is None
    encoded = json.dumps(output, ensure_ascii=False) + "".join(calls)
    for private in ("private@source.invalid", "777777777", "888888888", "secret-thread", "secret-handle", "secret-author"):
        assert private not in encoded
    assert output["customer_or_public_actions"] == 0 and output["suggest_only"] is True


def test_bucket_claim_restart_and_persistent_48h_strategy_clock(environment):
    args, calls = environment
    first = review.review_due(NOW, **args)
    start = artifact(args)["strategy_started_at"]
    assert first["slot"] == "2026-11-19-18"
    assert review.review_due(NOW + timedelta(minutes=1), **args)["status"] == "already_attempted"
    assert len(calls) == 2
    next_run = review.review_due(NOW + timedelta(hours=6), **args)
    assert next_run["slot"] == "2026-11-20-00" and len(calls) == 4
    assert artifact(args)["strategy_started_at"] == start
    assert datetime.fromisoformat(artifact(args)["evaluate_after"]) == NOW + timedelta(hours=48)
    assert artifact(args)["evaluation_due"] is False
    assert review.review_due(NOW, **args)["status"] == "already_attempted"  # backward clock never reopens a claim
    assert len(calls) == 4
    assert len(list(args["output_dir"].glob("*.json"))) == 3
    assert not list(args["output_dir"].glob("*.tmp"))


def test_evaluation_deadline_does_not_assert_goal_achievement(environment):
    args, _ = environment
    review.review_due(NOW, **args)
    review.review_due(NOW + timedelta(hours=48), **args)
    output = artifact(args)
    assert output["evaluation_due"] is True
    assert output["goals_status"] == "aspirational_not_verified"


def test_strategy_window_counts_new_activity_only_and_retains_baseline(environment):
    args, _ = environment
    review.review_due(NOW, **args)
    baseline = artifact(args)["baseline"]
    assert artifact(args)["goal_progress"]["new_customers_used"] == 0
    assert artifact(args)["goal_progress"]["answered_two_way_conversations"] == 0
    joined, event = ((NOW + timedelta(hours=h)).isoformat() for h in (1, 2))
    with sqlite3.connect(args["cashback_path"]) as conn:
        conn.execute("INSERT INTO telegram_users VALUES(303,?)", (joined,))
        conn.execute("INSERT INTO bot_state VALUES('src:303','threads_cb_save')")
        conn.execute("INSERT INTO link_requests VALUES(3,303,'c','created',?)", (event,))
    with sqlite3.connect(args["store_path"]) as conn:
        conn.execute("INSERT INTO users VALUES(304,?)", (joined,))
        conn.execute("INSERT INTO state VALUES('src:304','threads_ai_price')")
        conn.execute("INSERT INTO orders VALUES(3,304,?,'done',34000,0)", (event,))
    with sqlite3.connect(args["growth_path"]) as conn:
        conn.executemany("INSERT INTO followups VALUES('answered',?,3,'secret-new-author')", [(event,), (event,)])
        conn.executemany("INSERT INTO dm_messages VALUES('secret-new-thread','secret-handle',?,?)",
                         [("in", event), ("out", event)])
    review.review_due(NOW + timedelta(hours=6), **args)
    output = artifact(args)
    progress = output["goal_progress"]
    assert progress["answered_two_way_conversations"] == 2  # duplicate public followups are one conversation
    assert progress["new_customers_used"] == 2
    assert progress["threads_first_touch_new_customers_used"] == 2
    assert progress["new_customers_used_per_bot"] == {"cashbot": 1, "ai_store": 1}
    assert progress["qualified_two_way_conversations"] is None
    assert output["baseline"] == baseline
    assert output["goals"]["answered_two_way_conversations"] == 5
    with sqlite3.connect(args["cashback_path"]) as conn:
        conn.execute("INSERT INTO telegram_users VALUES(305,?)", ((NOW + timedelta(hours=49)).isoformat(),))
        conn.execute("INSERT INTO link_requests VALUES(4,305,'d','created',?)", ((NOW + timedelta(hours=50)).isoformat(),))
    review.review_due(NOW + timedelta(hours=54), **args)
    output = artifact(args)
    assert output["evidence"]["strategy_to_date"]["until"] == (NOW + timedelta(hours=48)).isoformat()
    assert output["goal_progress"]["new_customers_used"] == 2 and output["baseline"] == baseline


def test_unchanged_zero_evidence_still_gets_bounded_periodic_jobs(environment):
    args, calls = environment
    for key in ("cashback_path", "store_path"):
        with sqlite3.connect(args[key]) as conn:
            conn.execute("DELETE FROM " + ("telegram_users" if key == "cashback_path" else "users"))
    output = review.review_due(NOW, **args)
    assert output["status"] == "completed" and len(calls) == 2
    assert artifact(args)["evidence"]["windows"]["24h"]["business"]["groups"] == []
    assert artifact(args)["jobs"]["content"]["drafts"]


def test_lock_contention_makes_no_provider_calls(environment):
    args, calls = environment
    with args["state_path"].with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert review.review_due(NOW, **args) == {"status": "busy"}
    assert calls == [] and not args["state_path"].exists()


def test_provider_failure_falls_back_without_retry_same_bucket(environment):
    args, calls = environment

    def unavailable(prompt, **_kwargs):
        calls.append(prompt)
        raise RuntimeError("private provider context")

    args["generator"] = unavailable
    assert review.review_due(NOW, **args)["status"] == "partial"
    output = artifact(args)
    assert output["jobs"]["measurement"]["status"] == "ready"
    assert output["jobs"]["conversion"]["status"] == "unavailable"
    assert output["fallback_next_action"]
    assert "private provider context" not in json.dumps(output)
    assert review.review_due(NOW, **args)["status"] == "already_attempted"
    assert len(calls) == 2


def test_hard_interruption_after_role_claim_is_not_retried(environment):
    args, calls = environment

    def interrupted(prompt, **_kwargs):
        calls.append(prompt)
        raise KeyboardInterrupt()

    args["generator"] = interrupted
    with pytest.raises(KeyboardInterrupt):
        review.review_due(NOW, **args)
    status = review.review_due(NOW, **args)
    assert status["status"] == "already_attempted" and len(calls) == 1
    assert status["jobs"]["conversion"]["status"] == "attempting"
    assert artifact(args)["jobs"]["conversion"]["status"] == "attempting"


def test_missing_database_has_unavailable_status_not_false_zero(environment, tmp_path):
    args, _ = environment
    args["growth_path"] = tmp_path / "missing-growth.sqlite"
    args["store_path"] = tmp_path / "missing-store.sqlite"
    assert review.review_due(NOW, **args)["status"] == "partial"
    evidence = artifact(args)["evidence"]["windows"]["24h"]
    assert evidence["activity"]["status"] == "unavailable"
    assert "public_replies_sent" not in evidence["activity"]
    assert evidence["business"]["availability"]["ai_store"] == "unavailable"
    assert not args["growth_path"].exists() and not args["store_path"].exists()


def test_exclusion_configuration_is_explicit_and_invalid_value_fails_closed(environment):
    assert review.get_exclusions({}) == {"cashbot": (), "ai_store": ()}
    assert review.get_exclusions({"STORE_ADMIN_IDS": "1;2", "STORE_TEST_USER_IDS": "2,3",
                                  "CASHBACK_ADMIN_USER_IDS": "5", "CUSTOMER_NOTIFICATIONS_TEST_IDS": "-6"}) == {
                                      "cashbot": (-6, 5), "ai_store": (1, 2, 3)}
    with pytest.raises(ValueError):
        review.get_exclusions({"STORE_ADMIN_IDS": "bad"})
    args, _ = environment
    args["exclusions"] = {}
    review.review_due(NOW, **args)
    assert artifact(args)["evidence"]["exclusion_scope"]["cashbot"]["status"] == "not_configured"


@pytest.mark.parametrize("raw", ["plain non-JSON", '{"drafts":[]}', '{"experiments":[{"hypothesis":"secret@person.invalid"}]}'])
def test_invalid_model_output_is_unavailable_not_published(environment, raw):
    args, _ = environment
    args["generator"] = lambda *_a, **_kw: (raw, {"ok": True})
    review.review_due(NOW, **args)
    assert artifact(args)["status"] == "partial"
    assert artifact(args)["jobs"]["content"]["status"] == "unavailable"


def test_offer_context_exports_only_verified_catalog_attributes(environment):
    args, calls = environment
    with sqlite3.connect(args["store_path"]) as conn:
        conn.execute("CREATE TABLE products(id INTEGER,name TEXT,description TEXT)")
        conn.execute("INSERT INTO products VALUES(2,'Capcut Pro 30D acc cấp',"
                     "'Dùng tối đa2 thiết bị. private@catalog.invalid giá bí mật')")
    before = args["store_path"].read_bytes()
    review.review_due(NOW, **args)
    context = artifact(args)["evidence"]["offer_context"]
    assert context["ai_store"]["duration_days"] == 30
    assert context["ai_store"]["delivery"] == "tài khoản cấp sẵn"
    assert context["ai_store"]["max_devices"] == 2
    assert "link sản phẩm Shopee" in context["cashbot"]["purpose"]
    assert "private@catalog.invalid" not in json.dumps(context) + "".join(calls)
    assert args["store_path"].read_bytes() == before
    assert "QUY TẮC BẮT BUỘC" in calls[0] and "không có quyền gửi tin" in calls[0]


@pytest.mark.parametrize("draft", [
    "Dạ em chào anh/chị, em là trợ lý shop, sẵn sàng hỗ trợ anh chị ạ.",
    "Bạn cần tạo liên kết thanh toán Shopee để hoàn tất giao dịch không?",
    "Em thấy mình đang lỗi xuất video CapCut, bạn đã thử khởi động lại chưa?",
    "Bạn cần dùng CapCut30ngày cấp sẵn tối đa2 thiết bị để dựng video không?",
    "Shop có hỗ trợ CapCut cho anh/chị, em luôn sẵn sàng hỗ trợ.",
])
def test_semantic_gate_rejects_generic_wrong_domain_and_unverified_claims(environment, draft):
    args, _ = environment
    invalid = copy.deepcopy(CONTENT)
    invalid["drafts"][0]["draft"] = draft
    args["generator"] = lambda prompt, **_kw: (json.dumps(invalid if '"drafts"' in prompt else RESEARCH), {"ok": True})
    review.review_due(NOW, **args)
    assert artifact(args)["jobs"]["content"] == {
        "status": "unavailable", "reason": "semantic_quality_gate_failed", "needs_revision": True,
        "attempted_at": NOW.isoformat()}


@pytest.mark.parametrize("evidence", ["7d có2/89 khách dùng nên24h chuyển đổi2,2%", "Tỷ lệ24h yếu nên đổi CTA"])
def test_conversion_gate_rejects_invented_ratios_and_requires_two_lanes(environment, evidence):
    args, _ = environment
    invalid = copy.deepcopy(RESEARCH)
    invalid["experiments"][0]["evidence"] = evidence
    args["generator"] = lambda prompt, **_kw: (json.dumps(CONTENT if '"drafts"' in prompt else invalid), {"ok": True})
    review.review_due(NOW, **args)
    assert artifact(args)["jobs"]["conversion"]["reason"] == "semantic_quality_gate_failed"
    assert artifact(args)["jobs"]["content"]["status"] == "ready_for_review"


def test_quality_gate_does_not_retry_or_overwrite_an_existing_bucket(environment):
    args, calls = environment
    review.review_due(NOW, **args)
    original = artifact(args)
    original["jobs"]["content"]["drafts"][0]["draft"] = "Dạ em chào anh chị, em là trợ lý shop."
    latest = args["output_dir"] / "latest.json"
    history = args["output_dir"] / f"{original['slot']}.json"
    for path in (latest, history):
        path.write_text(json.dumps(original))
    before = [p.read_bytes() for p in (latest, history)]
    assert review.review_due(NOW, **args)["status"] == "already_attempted"
    assert len(calls) == 2 and [p.read_bytes() for p in (latest, history)] == before
