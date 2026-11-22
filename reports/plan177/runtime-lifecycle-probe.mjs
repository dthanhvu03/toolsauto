/** PLAN-177: bounded portal lifecycle evidence only; no credentials/raw bodies exported. */
import { readFile, writeFile } from 'node:fs/promises';
import { writeFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { getContext, closeContext } from 'file:///C:/Users/Admin/AppData/Roaming/npm/node_modules/@bintangtimurlangit/shopee-mcp/build/browser/session.js';
const output=new URL('runtime-lifecycle-20261119.json',import.meta.url);
const result={at:new Date().toISOString(),events:[],checks:[]};
const start=performance.now();
function mark(stage,fields={}){result.events.push({stage,elapsed_ms:Math.round(performance.now()-start),...fields});writeFileSync(output,JSON.stringify(result,null,2));}
function route(url){try{const u=new URL(url);if(u.origin==='https://affiliate.shopee.vn')return /auth|login|verify|captcha/.test(u.pathname)?'affiliate_auth_or_verification':u.pathname.startsWith('/offer/')?'affiliate_offer':'affiliate_other';return u.hostname==='shopee.vn'||u.hostname==='www.shopee.vn'?'buyer_origin':'other_origin';}catch{return 'unparseable';}}
function errorCode(error){const m=String(error?.message||error||'').match(/net::ERR_[A-Z_]+/);return m?m[0]:error?.name==='TimeoutError'?'timeout':/Execution context was destroyed/.test(error?.message||'')?'navigation_interrupted':'other_error';}
async function bounded(work,ms){let timer;try{return await Promise.race([work,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Object.assign(new Error('bounded'),{name:'TimeoutError'})),ms);})]);}finally{clearTimeout(timer);}}
const hard=setTimeout(()=>{result.error='hard_diagnostic_timeout';writeFileSync(output,JSON.stringify(result,null,2));process.exit(2);},65000);
try{
 mark('context_start');
 const ctx=await getContext();mark('context_ready',{pages:ctx.pages().length});
 const cookies=JSON.parse(await readFile(new URL('../../storage/db/config/shopee_affiliate_cookies.json',import.meta.url),'utf8'));
 await ctx.addCookies(Object.entries(cookies).map(([name,value])=>({name,value:String(value),domain:'.shopee.vn',path:'/',secure:true})));mark('cookie_sync_ready');
 const page=ctx.pages().find(x=>!x.isClosed())??await ctx.newPage();
 mark('page_adopted',{route:route(page.url())});
 page.on('domcontentloaded',()=>mark('domcontentloaded',{route:route(page.url())}));
 page.on('load',()=>mark('load',{route:route(page.url())}));
 page.on('framenavigated',frame=>{if(frame===page.mainFrame())mark('main_frame',{route:route(frame.url())});});
 page.on('requestfailed',req=>{if(req.resourceType()==='document')mark('document_failed',{route:route(req.url()),error:errorCode(req.failure()?.errorText)});});
 page.on('response',res=>{if(res.request().resourceType()==='document')mark('document_response',{route:route(res.url()),http:res.status()});});
 mark('goto_commit_start');
 try{const res=await page.goto('https://affiliate.shopee.vn/offer/product_offer',{waitUntil:'commit',timeout:15000});mark('goto_commit_done',{http:res?.status(),route:route(page.url())});}
 catch(error){mark('goto_commit_error',{code:errorCode(error),route:route(page.url())});}
 await page.waitForTimeout(800+Math.random()*500);
 const state=await bounded(page.evaluate(()=>({origin:location.origin==='https://affiliate.shopee.vn'?'affiliate':'other',path_type:/auth|login|captcha|verify/.test(location.pathname)?'auth_or_verification':location.pathname.startsWith('/offer/')?'offer':'other',ready:document.readyState,body_present:!!document.body})),5000);
 result.checks.push({kind:'document_state',...state});mark('document_state_ready');
 if(state.origin!=='affiliate'||state.path_type!=='offer'){result.error='portal_not_ready';}
 else{
  const quote=await bounded(page.evaluate(async()=>{
   const csrf=(document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)||[])[1]||'';
   try{const response=await fetch('/api/v3/offer/product?item_id=54321049804',{credentials:'include',headers:{'X-CSRFToken':csrf},signal:AbortSignal.timeout(8000)});const body=await response.json();if(body?.error===90309999||body?.code===90309999)return {http:response.status,error:'verification_required'};if(body.code!==0)return {http:response.status,code:body.code??null,error:'portal_rejected'};const d=body.data,c=d?.batch_item_for_item_card_full,r=d?.commission_rate_detail;return {http:response.status,code:body.code,item_id:String(d?.item_id||''),shop_id:String(c?.shopid||''),currency:c?.currency,status:c?.status,item_status:c?.item_status,name_present:typeof c?.name==='string'&&!!c.name,price_raw:c?.price,seller_rate_raw:r?.seller_commission_detail?.social_media_default_exist_commission_rate,platform_rate_raw:r?.shopee_commission_detail?.social_media_shop_base_exist_commission_rate,cap_raw:r?.channel_cap?.exist_user?.social_media_cap};}catch(e){return {error:e?.name==='TimeoutError'||e?.name==='AbortError'?'fetch_timeout':'fetch_failed'};}
  }),10000);result.checks.push({kind:'one_native_item',...quote});mark('native_fetch_done');
 }
}catch(error){result.error=errorCode(error);mark('diagnostic_error',{code:result.error});}
finally{mark('close_start');await closeContext();result.closed=true;mark('closed');clearTimeout(hard);await writeFile(output,JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify(result)+'\n');}
