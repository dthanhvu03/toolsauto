# PLAN-070: Key gói Free thì không gửi kèm bình luận đầu tiên

- Executor: Claude Code (Owner duyệt 2026-10-23 21:40 ICT, "oke thực hiện đi em")
- Status: Code xong, chờ key mở lại để thấy chạy thật

## Bối cảnh

`BufferAdapter.publish` (bài không phải TikTok) thực hiện theo thứ tự:

1. Gọi AI sinh bình luận đầu tiên.
2. Gửi `create_post` kèm bình luận. Gói Free trả lỗi "First comment requires a paid plan".
3. Gửi lại `create_post` không kèm bình luận.

Mỗi bài vì vậy tốn 2 request Buffer và 1 lần gọi AI vô ích. Cả 3 key đều là gói Free. Log 23/10: mọi job 1113–1132 đều có dòng "Bo first_comment (plan khong ho tro)".

## Scope

1. `adapter.py`: khi gặp lỗi paid plan thì ghi nhớ theo key (sha256 rút gọn, qua `cooldown_store`, khóa riêng `first_comment:<key>`) trong 7 ngày. Trong thời gian đó, bài của key này không sinh bình luận và không gửi kèm bình luận: chỉ 1 request, không gọi AI. Hết 7 ngày thì thử lại một lần, phòng khi Owner nâng gói.
2. `cooldown_store.py`: chỉ sửa docstring (file dùng chung cho mốc thời gian theo key).
3. Test trong `tests/test_buffer_first_comment.py`.

## Không làm

- Không đổi nội dung, cách sinh bình luận, luồng TikTok, luồng story.

## Rollback

Revert commit. Hoặc xóa các dòng `first_comment:` trong `storage/db/config/buffer_cooldown.json` (file chỉ lưu hash).

## Definition of Done

- Lỗi paid plan lần đầu: hành vi như cũ (gửi lại không kèm bình luận), đồng thời ghi nhớ key.
- Bài sau cùng key: `create_post` gọi 1 lần với `first_comment=None`, không gọi AI.
- Key khác (chưa ghi nhớ): vẫn thử kèm bình luận.
- Client giả không có `_key` dạng chuỗi: hành vi như cũ.
- Chạy thật: không còn dòng "Bo first_comment" sau lần đầu của mỗi key.

## Proof

2026-10-23, Claude Code:

- `tests/test_buffer_first_comment.py` thêm 4 test:
  - lỗi paid plan lần đầu vẫn tốn 2 request, lần sau cùng key chỉ 1 request với `first_comment=None` và không gọi AI;
  - key khác vẫn thử kèm bình luận;
  - quá `FIRST_COMMENT_RECHECK_SEC` thì thử lại;
  - client không có `_key` dạng chuỗi giữ hành vi cũ.
- Hồi quy pass:
  - first_comment, adversarial_first_comment, api, cooldown_store, rate_limit_guard, manager: 142 passed;
  - adversarial_m1, cluster_challenger, fuzz_probes, media, queue, slots, sync_posted, e2e_cluster, challenger_m1_r3: 550 passed.
- Restart 22:0x ICT, nhưng chưa thấy chạy thật: key 1 dính 429 ngay vòng đầu, khóa 79296s, mở lại khoảng 20:00 24/10. Bài đầu sau khi key mở lại sẽ còn một dòng "Bo first_comment"; từ bài sau trở đi phải hết.
