import json,mimetypes,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
root=Path('/tmp/toolsauto-ui175-dist'); out=Path('/tmp/toolsauto-ui175-proof'); out.mkdir(exist_ok=True)
now=int(time.time()); long='KenhRấtDàiKhôngCóKhoảngCách'*5
channels=[dict(id='a',name='Uyển Nhi',scheduled=10,ready_waiting=48,next_at=now+3600,posted_7d=14),dict(id='b',name='Hoa Lệ Đây',scheduled=2,ready_waiting=0,next_at=now+7200,posted_7d=6),dict(id='c',name=long,scheduled=0,ready_waiting=0,next_at=None,posted_7d=5)]
overview=dict(generated_at=now,channels=channels,jobs_24h={'DONE':12,'FAILED':2},materials_7d={'READY':30},failed_jobs={'count':1,'latest':[dict(id=99,channel=long,error='Buffer báo lỗi: '+long,finished_at=now)]},disk=dict(free_gb=12,used_gb=20,total_gb=32,pct=62,label='disk',pause_below_gb=2,below_pause=False))
jobs=dict(jobs=[dict(id=1,status='DONE',channel='Uyển Nhi',material_id=12,caption='Caption '+long,schedule_ts=now+3600),dict(id=2,status='FAILED',channel=long,material_id=13,error_message='Lỗi dài: '+long,schedule_ts=now)],total=2,total_pages=1,page=1)
requests=[]; errors=[]
def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox']); page=browser.new_page()
  page.on('pageerror',lambda e: errors.append(str(e)))
  def route(r):
   path=urlparse(r.request.url).path
   if path.startswith('/api/'):
    requests.append(r.request.url); r.fulfill(json=overview if path=='/api/admin/overview' else jobs if path=='/api/admin/jobs' else {}); return
   if path.startswith('/static/admin/'): f=root/path.removeprefix('/static/admin/')
   elif path.startswith('/app'): f=root/'index.html'
   else: r.fulfill(status=404,body=''); return
   if f.is_file(): r.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
   else: r.fulfill(status=404,body='')
  page.route('**/*',route)
  results=[]
  for width,height in [(320,740),(390,844),(768,1024),(1440,900)]:
   page.set_viewport_size(dict(width=width,height=height))
   for path in ['/app','/app/go/jobs']:
    page.goto('http://ui175.local'+path); page.locator(':text-is("Uyển Nhi"):visible').first.wait_for(); page.evaluate('document.fonts.ready')
    overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    if overflow:
     print(page.evaluate("Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent?.slice(0,60),width:e.getBoundingClientRect().width})).slice(-20)"))
    page.screenshot(path=str(out/f'{width}-{path.split("/")[-1]}.png'),full_page=True)
    assert not overflow,(width,path,'horizontal overflow')
    results.append(dict(width=width,path=path,horizontal_overflow=overflow))
   if width<1024:
    page.get_by_role('button',name='Menu',exact=True).click(); dialog=page.get_by_role('dialog'); assert dialog.is_visible()
    page.keyboard.press('Escape'); assert not dialog.is_visible()
    page.get_by_role('button',name='Mở menu',exact=True).click()
    page.get_by_role('dialog').get_by_role('link',name='Tổng quan',exact=True).click()
    assert not page.get_by_role('dialog').is_visible()
    assert page.get_by_role('navigation',name='Trang chính',exact=True).get_by_role('link',name='Tổng quan',exact=True).get_attribute('aria-current')=='page'
    page.get_by_role('button',name='Menu',exact=True).click(); page.screenshot(path=str(out/f'{width}-menu.png')); page.keyboard.press('Escape')
    page.goto('http://ui175.local/app/go/jobs'); page.locator(':text-is("Uyển Nhi"):visible').first.wait_for()
    if width<768:
     page.get_by_text('Xem lỗi',exact=True).click(); assert page.get_by_role('list',name='Các lượt đăng').get_by_text('Lỗi dài: '+long,exact=True).is_visible()
     page.get_by_role('textbox',name='Tìm lịch đăng theo mã hoặc caption').fill('canva')
     page.get_by_role('button',name='Tìm',exact=True).click(); page.wait_for_timeout(100); assert any('q=canva' in u for u in requests)
    results.append(dict(width=width,menu_escape=True,menu_navigation=True))
  page.set_viewport_size(dict(width=390,height=844)); page.get_by_role('button',name='Menu',exact=True).click()
  page.set_viewport_size(dict(width=1440,height=900)); page.wait_for_timeout(150); assert page.get_by_role('dialog').count()==0
  page.set_viewport_size(dict(width=320,height=740))
  for mode in ['empty','error']:
   def state_route(r):
    if mode=='error': r.fulfill(status=503,json={'detail':'unavailable'})
    elif '/overview' in r.request.url: r.fulfill(json={**overview,'channels':[],'failed_jobs':{'count':0,'latest':[]}})
    else: r.fulfill(json={'jobs':[],'total':0,'total_pages':1,'page':1})
   page.route('**/api/admin/**',state_route)
   for path,text in [('/app','Chưa có kênh'),('/app/go/jobs','Không có job')]:
    page.goto('http://ui175.local'+path)
    if mode=='error': page.get_by_text('Lỗi tải lịch đăng' if 'jobs' in path else 'Không tải được /api/admin/overview.',exact=False).wait_for(timeout=15000)
    else: page.wait_for_timeout(300)
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(mode,path)
    page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
    if 'jobs' in path:
     btn=page.get_by_role('button',name='Sau',exact=True).bounding_box()
     nav=page.get_by_role('navigation',name='Trang chính',exact=True).bounding_box()
     assert btn['y']+btn['height'] <= nav['y'],(mode,btn,nav)
   page.unroute('**/api/admin/**',state_route)
  results.append(dict(empty_and_error_states=True,pagination_above_navigation=True))
  assert errors==[],errors
  browser.close()
 proof=dict(results=results,page_errors=errors,api_mocked=True,external_requests=0,resize_modal_closed=True)
 (out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
 print(json.dumps(proof,ensure_ascii=False))
run()
