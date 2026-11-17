import json,mimetypes,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
root=Path('/tmp/toolsauto-ui175-dist'); out=Path('/tmp/toolsauto-ui175-proof2'); out.mkdir(exist_ok=True)
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
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']); page=browser.new_page()
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=urlparse(r.request.url).path
  if r.request.method!='GET':
   mutations.append(dict(path=path,method=r.request.method,body=r.request.post_data)); r.fulfill(json={'ok':True}); return
  if path in fixtures: r.fulfill(json=fixtures[path]); return
  if path.startswith('/static/admin/'): f=root/path.removeprefix('/static/admin/')
  elif path.startswith('/app'): f=root/'index.html'
  else: unknown.append(path); r.fulfill(status=404,body=''); return
  r.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
 page.route('**/*',route)
 for width,height in [(320,740),(390,844),(768,1024),(1440,900)]:
  page.set_viewport_size(dict(width=width,height=height))
  for path,marker in [('/app/go/studio','Duyệt'),('/app/go/viral','Thêm link'),('/app/go/viral-sources','Thêm nguồn')]:
   page.goto('http://ui175.local'+path); page.get_by_role('button',name=marker,exact=True).first.wait_for(); page.wait_for_timeout(200)
   overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
   if overflow: print(page.evaluate("Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent?.slice(0,50)})).slice(-20)"))
   assert not overflow,(width,path)
   page.screenshot(path=str(out/f'{width}-{path.split("/")[-1]}.png'),full_page=True)
   results.append(dict(width=width,path=path,horizontal_overflow=False))
 page.set_viewport_size(dict(width=390,height=844))
 page.goto('http://ui175.local/app/go/studio'); page.get_by_role('button',name='Duyệt',exact=True).click()
 toast=page.get_by_role('status'); toast.wait_for()
 box=toast.bounding_box(); nav=page.get_by_role('navigation',name='Trang chính',exact=True).bounding_box()
 assert box['y']+box['height']<nav['y']
 assert any(m['path']=='/studio/api/projects/11/approve' for m in mutations)
 page.goto('http://ui175.local/app/go/viral'); page.get_by_role('list',name='Video trong kho').get_by_role('button',name='Xử lý',exact=True).click()
 page.wait_for_timeout(150); assert any(m['path']=='/api/admin/viral/21/process' for m in mutations)
 page.on('dialog',lambda d:d.dismiss())
 before=len(mutations); page.get_by_role('list',name='Video trong kho').get_by_role('button',name='Xóa',exact=True).click(); assert len(mutations)==before
 page.goto('http://ui175.local/app/go/viral-sources'); card=page.get_by_role('list',name='Các nguồn video')
 card.get_by_role('button',name='Quét',exact=True).click(); page.wait_for_timeout(150); assert any(m['path']=='/api/admin/viral-sources/31/scan' for m in mutations)
 card.get_by_role('combobox',name='Page đích').select_option(''); page.wait_for_timeout(150); assert any(m['path'].endswith('/31/page') and json.loads(m['body'])=={'target_page':''} for m in mutations)
 before=len(mutations); card.get_by_role('button',name='Xóa',exact=True).click(); assert len(mutations)==before
 for path,key in [('/app/go/studio','/studio/api/projects'),('/app/go/viral','/api/admin/viral'),('/app/go/viral-sources','/api/admin/viral-sources')]:
  fixtures[key]={**fixtures[key], 'projects':[],'items':[],'counts':{}}
  page.goto('http://ui175.local'+path); page.wait_for_timeout(300); assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 assert errors==[],errors
 assert unknown==[],unknown
 browser.close()
proof=dict(results=results,mutations_mocked=mutations,page_errors=errors,unknown_requests=unknown,toast_above_nav=True,delete_cancel_preserved=True,empty_states=True)
(out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)); print(json.dumps(proof,ensure_ascii=False))
