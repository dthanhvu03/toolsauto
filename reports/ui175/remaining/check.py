import json,mimetypes,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
root=Path('/tmp/toolsauto-ui175-dist'); out=Path('/tmp/toolsauto-ui175-proof-rest'); out.mkdir(exist_ok=True)
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

dt=dict(name='hook_library',label='Thư viện hook',module='Video',fields=[dict(fieldname='title',label='Tên',fieldtype='data')],is_child=False,title_field='title',naming='autoincrement',records=1)
spec=dict(v=1,canvas=dict(w=1080,h=1920,fps=30,fit='blur_pad',lut=None),clips=[],subtitles=dict(enabled=True,source='lines',lines=[],edits={},font_size=48,margin_v=80,max_chars=20),texts=[],audio=dict(original=1,tracks=[]),logo=None,credit=None)
fixtures['/studio/api/setup'].update(buffer_channels=[],template_kinds=[],luts=[])
fixtures.update({
'/studio/api/projects/11':dict(project={**project,'editable':True,'rendered_at':None},spec=spec,asset=None,assets=[],channel=dict(id=1,name='Uyển Nhi'),template=None,subtitle_lines=[dict(start=0,end=2,text='Phụ đề ví dụ')],luts=[],variants_allowed=False,group=dict(root_id=11,members=[]),tasks=[]),
'/studio/api/doc/config':dict(default_language='vi',preview_sec=30,canvas='9:16',sources=[],ai_keywords=False,rights_ok='ok',rights_need_proof=True,languages=[dict(code='vi',label='Tiếng Việt')],settings_url='/app/settings'),
'/api/admin/logs':dict(events=[dict(ts_unix=now,timestamp='',source='publisher',level='ERROR',job_id=12,message='Lỗi dài '+long)],total=1,total_pages=1,page=1),
'/api/admin/ai-studio':dict(personas=[dict(id='p',key='persona_main',label='Trợ lý',preview='Nội dung mẫu',chars=12,value='Nội dung mẫu')],configs=[],platforms=[]),
'/compliance/analytics':dict(total_keywords=0,total_violations=0,blocked_today=0,rewritten_count=0),'/compliance/keywords':[],'/compliance/categories':[],
'/api/doctypes':dict(doctypes=[dt],fieldtypes=['data','text','int']),'/api/doctypes/hook_library':dt,
'/api/doc/hook_library':dict(doctype=dt,records=[dict(name='1',title='Ví dụ',data=dict(title='Ví dụ'),created_at=now,modified_at=now)],total=1),
'/api/doc/hook_library/1':dict(name='1',doctype='hook_library',data=dict(title='Ví dụ'),created_at=now,modified_at=now)
})
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page()
 page.on('pageerror',lambda e:errors.append(dict(url=page.url,error=str(e))))
 def route(r):
  path=urlparse(r.request.url).path
  if path in fixtures:r.fulfill(json=fixtures[path]);return
  if path.startswith('/static/admin/'):f=root/path.removeprefix('/static/admin/')
  elif path.startswith('/app'):f=root/'index.html'
  else:unknown.append(path);r.fulfill(status=404,body='');return
  r.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
 page.route('**/*',route)
 routes=['studio/11','studio-assets','studio-setup','studio-tiktok','studio-doc','logs','ai-studio','compliance','telegram','doctype','doctype/new','doctype/hook_library','doc/hook_library','doc/hook_library/new','doc/hook_library/1']
 for w,h in [(320,740),(390,844),(768,1024),(1440,900)]:
  page.set_viewport_size(dict(width=w,height=h))
  for path in routes:
   page.goto('http://ui175.local/app/go/'+path);page.wait_for_timeout(200)
   assert page.locator('h1:visible').count()>0,path
   if path=='studio/11':
    assert page.locator('input[type=range]').evaluate_all('els=>els.every(e=>e.getBoundingClientRect().right<=innerWidth)'),w
   if path=='doc/hook_library' and w<768:
    page.get_by_role('list',name='Danh sách bản ghi').get_by_role('button').click();page.get_by_role('heading',name='Thư viện hook: 1',exact=True).wait_for()
   overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
   if overflow:print(page.evaluate("Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent?.slice(0,60)})).slice(-20)"))
   assert not overflow,(w,path)
   assert not page.get_by_text('Lỗi tải',exact=False).count(),path
   if w==390:page.screenshot(path=str(out/(path.replace('/','-')+'.png')),full_page=True)
   results.append(dict(width=w,path=path,horizontal_overflow=False))
 assert errors==[],errors
 assert unknown==[],unknown
 browser.close()
proof=dict(results=results,page_errors=errors,unknown_requests=unknown,api_mocked=True)
(out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps(proof,ensure_ascii=False))
