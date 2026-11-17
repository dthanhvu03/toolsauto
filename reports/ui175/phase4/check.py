import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
out=Path('/tmp/toolsauto-ui175-proof4'); out.mkdir(exist_ok=True)
state=dict(paused=False,phase='BOARDING',phase_left=120,bus=dict(no=1,riders=0,seats=[None]*24,lane='Hướng Bắc',arrow='↑'),trip_likes=12345,delivered=100,control={},tiktok=dict(state='idle'),music_tracks=[],reliefs=[],sim_rate=0)
errors=[]; mutations=[]; results=[]
with sync_playwright() as p:
 br=p.chromium.launch(headless=True,args=['--no-sandbox']); page=br.new_page()
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=urlparse(r.request.url).path
  if path=='/control':r.fulfill(body=Path('xe_tet/server/control.html').read_text(),content_type='text/html')
  elif path=='/api/state':r.fulfill(json=state)
  elif path=='/api/passengers':r.fulfill(json=dict(buses=[],queues=[]))
  elif r.request.method=='POST':
   mutations.append(json.loads(r.request.post_data));r.fulfill(json={'ok':True})
  else:r.fulfill(status=404,body='')
 page.route('**/*',route)
 for w,h in [(320,740),(390,844),(768,1024),(1440,900)]:
  page.set_viewport_size(dict(width=w,height=h));page.goto('http://xe175.local/control');page.wait_for_timeout(250)
  assert page.locator('#s-phase').inner_text()!='Mất kết nối'
  # Inspect every settings group while expanded, too.
  page.evaluate("document.querySelectorAll('details').forEach(e=>e.open=true)")
  overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
  if overflow:print(page.evaluate("Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,cls:e.className,text:e.textContent?.slice(0,70)})).slice(-20)"))
  assert not overflow,w
  assert page.locator('#dock button').evaluate_all('els=>els.every(e=>e.getBoundingClientRect().height>=44)')
  page.screenshot(path=str(out/f'{w}-control.png'),full_page=True)
  page.evaluate('scrollTo(0,document.body.scrollHeight)');last=page.get_by_role('button',name='Xoá hết dữ liệu',exact=False)
  results.append(dict(width=w,horizontal_overflow=False,all_settings_expanded=True,dock_targets_44px=True))
 page.locator('#q-pause').click();page.wait_for_timeout(100);assert any(m['action']=='pause' for m in mutations),mutations
 assert errors==[],errors
 br.close()
proof=dict(results=results,page_errors=errors,mutations_mocked=mutations,live_server_not_used=True)
(out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps(proof,ensure_ascii=False))
