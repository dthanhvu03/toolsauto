"""
Bất biến đồng thời của hàng đợi (AUDIT-001 §19, ADR-011).

TEST A — 1 job PENDING, 2 worker claim đồng thời → đúng 1 worker nhận được.
TEST B — 2 job KHÁC NHAU cùng (account, platform), 2 worker claim đồng thời →
         tối đa 1 job RUNNING.

Hai test này là điều kiện đóng của P0-1. Chúng phải chạy trên **PostgreSQL thật**,
không mock: lỗi nằm ở tầng khoá của Postgres (EvalPlanQual), mock không tái hiện nổi.

⚠️ TEST B là một race RIÊNG, KHÔNG được bảo vệ bởi bản vá của TEST A. Khi hai worker
chọn hai row khác nhau thì không có xung đột khoá nên EvalPlanQual không bao giờ
chạy, và outer predicate vô tác dụng. TEST B chỉ xanh khi có partial unique index
`(account_id, platform) WHERE status='RUNNING'` và claim bắt được IntegrityError.

Cô lập: mỗi ca dùng `platform` tag riêng (`__pytest_race_*`) và câu claim lọc theo
`j.platform = :platform`, nên không bao giờ chạm job production.
"""
from __future__ import annotations

import threading
import time
import uuid

import pytest

pytestmark = pytest.mark.integration

TAG_PREFIX = "__pytest_race_"


def _session_or_skip():
    try:
        from sqlalchemy import text

        from app.core.database.core import SessionLocal

        s = SessionLocal()
        s.execute(text("SELECT 1"))
        return s
    except Exception as e:  # pragma: no cover - phụ thuộc môi trường
        pytest.skip(f"Không có Postgres để chạy test race: {e}")


@pytest.fixture()
def db():
    session = _session_or_skip()
    created_account_ids: list[int] = []
    try:
        yield session, created_account_ids
    finally:
        from sqlalchemy import text

        session.rollback()
        if created_account_ids:
            session.execute(
                text(
                    "DELETE FROM job_events WHERE job_id IN "
                    "(SELECT id FROM jobs WHERE account_id = ANY(:ids))"
                ),
                {"ids": created_account_ids},
            )
            session.execute(
                text("DELETE FROM jobs WHERE account_id = ANY(:ids)"), {"ids": created_account_ids}
            )
            session.execute(
                text("DELETE FROM accounts WHERE id = ANY(:ids)"), {"ids": created_account_ids}
            )
            session.commit()
        session.close()


def _make_account(session, created_ids, tag):
    from app.core.database.models import Account

    account = Account(
        name=f"{tag}_acc",
        platform="facebook",
        is_active=True,
        login_status="ACTIVE",
        cooldown_seconds=0,
    )
    session.add(account)
    session.flush()
    created_ids.append(account.id)
    session.commit()
    return account.id


def _make_job(session, account_id, tag, schedule_ts):
    from app.core.database.models import Job

    job = Job(
        platform=tag,
        account_id=account_id,
        job_type="POST",
        status="PENDING",
        caption="pytest race guard",
        schedule_ts=schedule_ts,
    )
    session.add(job)
    session.commit()
    return job.id


def _claim_blocked_by_uncommitted_winner(session, tag, job_id):
    """
    Tái hiện TẤT ĐỊNH cảnh "worker khác đã claim job này trước".

    Không dùng barrier vì cửa sổ race chỉ vài trăm micro-giây — thắng thua phụ
    thuộc lịch OS, test sẽ xanh giả. Thay vào đó dựng đúng trạng thái mà race tạo ra:

      T1  UPDATE job -> RUNNING, CHƯA commit
      T2  claim_next_job: snapshot READ COMMITTED vẫn thấy job PENDING nên subquery
          chọn đúng nó, rồi UPDATE ngoài chặn ở khoá dòng của T1
      T1  commit  -> T2 tỉnh dậy và chạy lại EvalPlanQual

    Đây chính là thời điểm quyết định: outer qual `id = $0` vẫn đúng trên bản ghi
    mới nên T2 ghi đè job đang RUNNING. Thêm `status='PENDING'` vào qual ngoài thì
    lần kiểm lại thất bại và T2 trả 0 dòng.
    """
    from sqlalchemy import text

    from app.core.database.core import SessionLocal
    from app.core.queue.queue import QueueService

    winner = SessionLocal()
    winner.execute(
        text(
            "UPDATE jobs SET status='RUNNING', "
            "locked_at=CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER), "
            "last_heartbeat_at=CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER) "
            "WHERE id = :id"
        ),
        {"id": job_id},
    )  # cố ý CHƯA commit: giữ khoá dòng

    outcome: dict = {}

    def loser():
        s = SessionLocal()
        try:
            s.execute(text("SELECT 1"))  # mở kết nối trước khi vào vùng chặn
            job = QueueService.claim_next_job(s, platform=tag)
            outcome["job_id"] = job.id if job is not None else None
        except Exception as exc:
            outcome["error"] = exc
        finally:
            s.close()

    thread = threading.Thread(target=loser)
    thread.start()
    time.sleep(1.0)  # đủ để T2 chạm khoá và nằm chờ
    winner.commit()
    thread.join(timeout=30)
    winner.close()
    assert not thread.is_alive(), "worker thua treo, không thoát khỏi khoá dòng"
    return outcome


def _running_count(session, tag):
    from sqlalchemy import text

    session.commit()  # thoát khỏi snapshot cũ để thấy commit của luồng khác
    return session.execute(
        text("SELECT COUNT(*) FROM jobs WHERE platform = :tag AND status = 'RUNNING'"),
        {"tag": tag},
    ).scalar()


def test_a_two_workers_cannot_claim_the_same_job(db):
    """TEST A — một job PENDING chỉ được đúng một worker nhận."""
    session, created = db
    tag = f"{TAG_PREFIX}{uuid.uuid4().hex[:8]}"
    account_id = _make_account(session, created, tag)
    job_id = _make_job(session, account_id, tag, int(time.time()) - 60)

    outcome = _claim_blocked_by_uncommitted_winner(session, tag, job_id)

    assert "error" not in outcome, f"claim ném lỗi: {outcome.get('error')!r}"
    assert outcome["job_id"] is None, (
        f"worker thua vẫn claim được job {outcome['job_id']} đang RUNNING. "
        "Hai worker cùng giữ một job nghĩa là bài sẽ được đăng hai lần."
    )
    assert _running_count(session, tag) == 1


def test_b_two_jobs_same_account_platform_cannot_both_run(db):
    """
    TEST B — hai job KHÁC NHAU cùng (account, platform) không được cùng RUNNING.

    Đây là race RIÊNG, bản vá của TEST A không che được: hai worker chọn hai dòng
    khác nhau thì không có xung đột khoá, EvalPlanQual không bao giờ chạy.

      T1  UPDATE job_khoa -> RUNNING, CHƯA commit
      T2  claim_next_job: `NOT EXISTS ... RUNNING` chưa thấy T1 nên coi account rảnh,
          và vì job_muc_tieu có schedule_ts sớm hơn nên nó chọn ĐÚNG dòng kia
      T1  commit

    Không có partial unique index: T2 commit thẳng -> hai job cùng RUNNING trên một
    tài khoản, hai browser cùng thao tác.
    Có index: T2 chặn ở khoá index rồi nhận unique violation khi T1 commit — nên
    `claim_next_job` BẮT BUỘC phải bắt IntegrityError và trả None.

    Lệch so với §19: audit đề xuất đặt schedule_ts BẰNG NHAU để ép hoà khoá sắp xếp.
    Hoà thì việc claim chọn dòng nào là không xác định, test sẽ lúc đỏ lúc xanh. Đặt
    job mục tiêu sớm hơn khiến nó luôn được chọn — vẫn đúng bất biến cần bảo vệ, mà
    tất định.
    """
    session, created = db
    tag = f"{TAG_PREFIX}{uuid.uuid4().hex[:8]}"
    account_id = _make_account(session, created, tag)
    now = int(time.time())
    job_khoa = _make_job(session, account_id, tag, now - 60)
    job_muc_tieu = _make_job(session, account_id, tag, now - 120)  # sớm hơn -> claim chọn nó

    outcome = _claim_blocked_by_uncommitted_winner(session, tag, job_khoa)

    assert "error" not in outcome, (
        f"claim ném lỗi thay vì trả None: {outcome.get('error')!r}. "
        "IntegrityError do partial unique index phải được bắt và trả None."
    )
    running = _running_count(session, tag)
    assert running <= 1, (
        f"{running} job cùng RUNNING trên một (account, platform); "
        f"claim nhận job {outcome.get('job_id')} trong khi job {job_khoa} đang chạy. "
        "Hai browser sẽ cùng thao tác trên một tài khoản."
    )
    assert job_muc_tieu is not None
