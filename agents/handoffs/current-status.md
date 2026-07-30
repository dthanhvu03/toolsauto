# Current Status

## System State

- Local: **http://127.0.0.1:8002** (web only khi `start.ps1`)
- Legacy content folders soft-retired: `videos/`, `done/`, `failed/` (ẩn System panel, không mkdir)
- Vẫn dùng: `media/`, `processed/`, `outputs/`, `reup/`

## Done This Session

- Soft-retire `videos/` + `done/` + `failed/` (panel/docs/config mkdir)
- Sửa docstring cleanup: delete in place, không archive vào `done/`/`failed/`
- Alias config giữ để compat; không xóa folder vật lý trên đĩa

## Next Action

1. Anh dùng UI → `…/content/media/` hoặc Viral → `storage/media/reup/`
2. Commit khi yêu cầu
