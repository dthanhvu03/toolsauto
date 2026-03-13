# UI/UX pages (HTMX-first)

## Pages
1) /dashboard
- Cards: jobs today, pending, failed, done
- Accounts active
- Recent failures list

2) /jobs
- Filter: status, date range (simple)
- Table: id, schedule, platform, account, status badge, tries, actions
- Actions:
  - Retry (POST /jobs/{id}/retry)
  - Reschedule (POST /jobs/{id}/reschedule)
  - Edit caption (modal or inline)
- HTMX polling: refresh table/rows every 10s

3) /content
- Upload file
- Inbox list (files found)
- Create job from file (choose schedule/account/caption mode)
- Move file to processed automatically after job created

4) /accounts
- List accounts
- Toggle active
- Set daily_limit, cooldown

## HTMX patterns
- Partial template: jobs/row.html, jobs/table.html
- hx-target per-row: update only one row after retry

## Tailwind conventions
- Use consistent components: badges, buttons, cards
- Avoid custom CSS unless needed
- Keep dark mode optional

## Acceptance criteria
- Không reload page khi thao tác job
- Action trả về HTML fragment đúng để swap