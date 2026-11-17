import json,mimetypes,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
root=Path('/tmp/toolsauto-ui175-dist'); out=Path('/tmp/toolsauto-ui175-proof3'); out.mkdir(exist_ok=True)
now=int(time.time()); long='KenhKhongCoKhoangCach'*5
project=dict(id=11,status='REVIEW',channel=long,channel_id=1,caption='Nội dung '+long,hashtags=[],duration=30,error=None,has_video=False,parent_project_id=None,tags=[])
fixtures={
'/studio/api/projects':dict(projects=[project],counts={'REVIEW':1},tasks_pending=0),
'/studio/api/setup':dict(channels=[dict(id=1,name=long)],luts=[],templates=[]),
'/studio/api/voices':dict(voices=[]),'/studio/api/assets':dict(assets=[]),'/studio/api/jobs':dict(jobs=[],active=0,now=now),
'/api/admin/viral':dict(items=[dict(id=21,url='https://video.example/'+long,status='NEW',views=1200,account_name=long)],total=1,total_pages=1,page=1),
'/api/admin/viral-sources':dict(items=[dict(id=31,platform='tiktok',url='https://example.com/'+long,handle=long,target_pages=['1'],enabled=True,last_scanned_at=now,last_found=3)],total=1,pages=[dict(id='1',name=long,slots='3')]),
}
errors=[]; mutations=[]; unknown=[]; results=[]

fixtures.update({
'/api/settings/metadata':{'fields':[
 dict(key='DISPLAY_NAME',label='Tên hiển thị',section='general',sectionLabel='Chung',type='string',defaultValue='ToolsAuto'),
 dict(key='VERY_LONG_SETTING_KEY_FOR_CONNECTION_TIMEOUT_TEST',label='Địa chỉ kết nối dịch vụ',section='connection',sectionLabel='Kết nối',type='url',defaultValue='https://example.com'),
 dict(key='SECRET',label='Mật khẩu dịch vụ',section='connection',type='secret',secret=True,defaultValue=''),
]},
'/api/settings/values':dict(values={'DISPLAY_NAME':'ToolsAuto','VERY_LONG_SETTING_KEY_FOR_CONNECTION_TIMEOUT_TEST':'https://example.com'},secrets={'SECRET':{'hasValue':True}}),
'/api/admin/database':dict(tables=[dict(name='video_materials',count=1500)],total=1),
'/api/admin/database/tables/video_materials':dict(columns=['id','title'],rows=[dict(id=1,title='Example')],total_rows=1),
'/threads-growth/api/overview':dict(enabled=False,worker=dict(scan_interval_min=10,auto_post_min_relevance=80,max_post_age_hours=24,vietnamese_only=True),limits=dict(max_replies_per_day=20,max_replies_per_hour=3,min_relevance=50),login=dict(ready=True,logging_in=False,login_status='ready'),quota=dict(posted_last_day=4,posted_last_hour=1,allowed=True),stats={},counts=dict(pending=0,approved=0,posted=0,failed=0),customers=dict(last_24h=0,total=0,active=0,by_variant={},by_channel={},customers=[],errors=[]),accounts=[]),
'/threads-growth/api/posts':dict(items=[]),'/threads-growth/api/own-posts':dict(items=[]),'/threads-growth/api/followups':dict(items=[]),
'/bot-users/api/report':dict(active_days=7,bots=[dict(bot='cashbot_tg',label='Cashbot TG',total=10,new_24h=1,new_7d=2,active_7d=5,buyers=1)],total=dict(bot='all',label='Tổng',total=10,new_24h=1,new_7d=2,active_7d=5,buyers=1),days=[dict(day='17/11',cashbot_tg=1,cashbot_zalo=0,ai_store=0)],sources={},people=[],matched=0,errors=[]),
'/api/admin/processes':dict(machine=dict(cpu_pct=12,cpus=4,mem_total_mb=16000,mem_used_mb=8000,gpu=None),apps=[dict(name='Web_Dashboard',label='Web dashboard',role='Giao diện',status='online',cpu=1,mem_mb=100,uptime_s=600,restarts=0,can_start=False,can_stop=True,can_restart=True)],services=[],error=None),
'/api/admin/processes/windows':dict(available=False,error=None),
'/api/admin/syspanel':dict(cpu=10,mem_pct=40,mem_used_gb=4,mem_total_gb=10,disk_pct=50,disk_used_gb=50,disk_total_gb=100,disk_label='WSL',jobs={})
})
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']); page=browser.new_page()
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=urlparse(r.request.url).path
  if r.request.method!='GET':
   mutations.append(dict(path=path,method=r.request.method,body=r.request.post_data)); r.fulfill(json={'ok':True,'updated':['DISPLAY_NAME']}); return
  if path in fixtures: r.fulfill(json=fixtures[path]); return
  if path.startswith('/static/admin/'): f=root/path.removeprefix('/static/admin/')
  elif path.startswith('/app'): f=root/'index.html'
  else: unknown.append(path); r.fulfill(status=404,body=''); return
  r.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
 page.route('**/*',route)
 for width,height in [(320,740),(390,844),(768,1024),(1440,900)]:
  page.set_viewport_size(dict(width=width,height=height))
  for path,marker in [('/app/settings','Cài đặt vận hành'),('/app/go/threads-growth','Threads — Kéo khách'),('/app/go/bot-users','Khách các bot'),('/app/go/database','SQL console'),('/app/go/syspanel','Panel hệ thống')]:
   page.goto('http://ui175.local'+path); page.locator(':text-is('+json.dumps(marker,ensure_ascii=False)+'):visible').first.wait_for(); page.wait_for_timeout(250)
   overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
   if overflow: print(page.evaluate("Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent?.slice(0,60)})).slice(-20)"))
   assert not overflow,(width,path)
   page.screenshot(path=str(out/f'{width}-{path.split("/")[-1]}.png'),full_page=True)
   results.append(dict(width=width,path=path,horizontal_overflow=False))
 page.set_viewport_size(dict(width=390,height=844)); page.goto('http://ui175.local/app/settings')
 page.get_by_role('combobox',name='Đến nhóm cài đặt').select_option('connection'); page.wait_for_timeout(300)
 assert page.evaluate('document.querySelector("#section-connection").getBoundingClientRect().top')<500
 page.locator('#section-general input[type=text]').fill('ToolsAuto mới')
 bar=page.get_by_role('status',name='').filter(has_text='Có thay đổi chưa lưu.'); bar.wait_for()
 nav=page.get_by_role('navigation',name='Trang chính',exact=True).bounding_box(); assert bar.bounding_box()['y']<nav['y']
 page.locator('#section-general').get_by_role('button',name='Save section',exact=True).click(); page.wait_for_timeout(200)
 assert any(m['path']=='/api/settings/sections/general' and json.loads(m['body'])=={'DISPLAY_NAME':'ToolsAuto mới'} for m in mutations),mutations
 page.goto('http://ui175.local/app/go/database'); page.get_by_role('list',name='Danh sách bảng').get_by_role('button').click(); page.get_by_text('Preview video_materials',exact=True).wait_for()
 assert not any(m['path'].endswith('/sql') for m in mutations)
 assert errors==[],errors
 assert unknown==[],unknown
 browser.close()
proof=dict(results=results,mutations_mocked=mutations,page_errors=errors,unknown_requests=unknown,settings_jump=True,unsaved_above_navigation=True,database_preview=True,sql_not_run=True)
(out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)); print(json.dumps(proof,ensure_ascii=False))
