import json
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import urlparse
from jinja2 import Environment,FileSystemLoader,select_autoescape
from playwright.sync_api import sync_playwright
out=Path('/tmp/toolsauto-ui175-proof56');out.mkdir(exist_ok=True)
env=Environment(loader=FileSystemLoader('app/templates'),autoescape=select_autoescape(['html']))
config=NS(CDN_TAILWIND='/mock-tailwind.js',CDN_HTMX='/mock-htmx.js',CDN_GOOGLE_FONTS='/fonts.css')
long='KhachHangTenRatDaiKhongKhoangCach'*3
person=dict(user_id=123,label=long,segment='active',channel='telegram',joined='2026-11-17',last_active='2026-11-17',links=12,clicks=40,orders=3,cancelled=1,gmv=1500000,net=120000,cashback=60000,margin=50000,wallet=20000,requested=10000,flags=['Cần kiểm tra'])
def render(name,path):
 return env.get_template(name).render(request=NS(url=NS(path=path),query_params={}),config=config,people=[person],total=1,counts={'active':1},segments={'active':'Đang dùng'},sorts={'margin':'Biên'},sort='margin',segment='',q='',channel='',vnd=lambda v:f'{v:,}đ',when=lambda v:v)
html={'/cashback/users':render('pages/cashback_users.html','/cashback/users'),'/app/logs':render('pages/app_logs.html','/app/logs')}
errors=[];results=[]
with sync_playwright() as p:
 br=p.chromium.launch(headless=True,args=['--no-sandbox']);page=br.new_page()
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=urlparse(r.request.url).path
  if path in html:r.fulfill(body=html[path],content_type='text/html')
  elif path=='/mock-tailwind.js':r.fulfill(body='window.tailwind={config:{}};',content_type='application/javascript')
  elif path=='/mock-htmx.js':r.fulfill(body='window.htmx={trigger:()=>{}};',content_type='application/javascript')
  elif path.endswith('.css'):
   body=Path('/tmp/ui175-jinja.css').read_text()
   if path=='/static/cave-tokens.css':body=Path('app/static/cave-tokens.css').read_text()
   r.fulfill(body=body,content_type='text/css')
  else:r.fulfill(body='',content_type='text/plain')
 page.route('**/*',route)
 for w,h in [(320,740),(390,844),(768,1024),(1440,900)]:
  page.set_viewport_size(dict(width=w,height=h))
  for path in html:
   page.goto('http://jinja175.local'+path);page.add_style_tag(path='/tmp/ui175-jinja.css');page.wait_for_timeout(100)
   assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(w,path)
   if w<1024:
    opener=page.get_by_role('button',name='Mở menu',exact=True);opener.click();dialog=page.get_by_role('dialog',name='Menu ToolsAuto');assert dialog.is_visible()
    assert page.evaluate('document.body.style.overflow')=='hidden'
    buttons=dialog.locator('a[href],button');buttons.last.focus();page.keyboard.press('Tab');assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
    page.keyboard.press('Escape');assert not dialog.is_visible();assert opener.evaluate('(e)=>e===document.activeElement')
    page.get_by_role('button',name='Menu',exact=True).click();page.set_viewport_size(dict(width=1440,height=h));page.wait_for_timeout(100);assert page.get_by_role('dialog').count()==0;assert page.evaluate('document.body.style.overflow')!='hidden';page.set_viewport_size(dict(width=w,height=h))
   if path=='/cashback/users' and w<768:
    card=page.get_by_role('list',name='Khách Cashback');card.get_by_text('Chi tiết hoạt động & tiền',exact=True).click();assert card.get_by_text('Hoa hồng ròng',exact=True).is_visible()
   if path=='/app/logs':
    for tab in ['Domain Events','PM2 Logs','AI Analytics']:
     page.get_by_role('tab',name=tab,exact=True).click();assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(w,tab)
   page.screenshot(path=str(out/f'{w}-{path.split("/")[-1]}.png'),full_page=True)
   results.append(dict(width=w,path=path,horizontal_overflow=False,drawer_checked=w<1024))
 assert errors==[],errors
 br.close()
proof=dict(results=results,page_errors=errors,jinja_rendered=True,tailwind_compiled_locally=True,api_mocked=True,cashback_details=True,logs_tabs=True)
(out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps(proof,ensure_ascii=False))
