/** PLAN-177 Gate B read-only POC. Run only while shopee-mcp is stopped.
 * Uses its existing profile; no credentials, headers, raw responses or product names exported.
 * JSON-line stdio only; no listening socket or installed npm edits.
 */
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { closeContext, getContext, withPage } from 'file:///C:/Users/Admin/AppData/Roaming/npm/node_modules/@bintangtimurlangit/shopee-mcp/build/browser/session.js';
const input = readFileSync(0,'utf8').trim().split(String.fromCharCode(10));
const origin = 'https://affiliate.shopee.vn';
async function probe(command) {
  return withPage(async page => {
    if (new URL(page.url()).origin !== origin) {
      await page.goto(origin + '/offer/product_offer', {waitUntil:'domcontentloaded',timeout:25000});
    }
    await page.waitForLoadState('networkidle',{timeout:8000}).catch(()=>{});
    await page.waitForTimeout(2500 + Math.random()*1500);
    return page.evaluate(async command => {
      if (location.origin !== 'https://affiliate.shopee.vn') return {error:'portal_login_required',origin:location.origin,path:location.pathname};
      const csrf=(document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)||[])[1]||'';
      if(command.kind==='surface') {
        return {path:location.pathname,inputs:Array.from(document.querySelectorAll('input')).map(x=>({placeholder:x.placeholder,type:x.type})),scripts:Array.from(document.scripts).map(x=>x.src).filter(x=>x.includes('/shopee-affiliate-live-vn/static/')).map(x=>x.split('?')[0])};
      }
      if(command.kind==='assets') {
        const urls = Array.from(document.scripts).map(x=>x.src).filter(x=>x && /affiliate.shopee.vn|shopee.sg/.test(new URL(x).hostname));
        const found=[];
        for(const url of urls.slice(0,14)) {
          try {
            const text=await (await fetch(url,{signal:AbortSignal.timeout(10000)})).text();
            const matches=[...text.matchAll(/.{0,180}(?:offer\/product\/|GetProductOfferList|productOfferList|product_detail).{0,220}/g)].slice(0,18).map(m=>m[0]);
            if(matches.length)found.push({asset:new URL(url).pathname,matches});
          } catch {}
        }
        return {found};
      }
      const params = new URLSearchParams({list_type:'0',sort_type:'1',page_offset:'0',page_limit:'50',client_type:'1',...(command.params||{})});
      const allowed=['list_type','sort_type','page_offset','page_limit','client_type','keyword','shop_id','item_id','shopid','itemid','product_link','product_url','url','match_type','match_id','filter_types'];
      if([...params.keys()].some(k=>!allowed.includes(k)))return {error:'disallowed_parameter'};
      const response = await fetch((command.kind==='detail'?'/api/v3/offer/product':'/api/v3/offer/product/list')+'?'+(command.kind==='detail'?new URLSearchParams({item_id:params.get('item_id')}):params).toString(),{credentials:'include',headers:{'X-CSRFToken':csrf},signal:AbortSignal.timeout(15000)});
      const body=await response.json();
      if(body.code!==0)return {http:response.status,code:body.code,error:'portal_error',envelope_keys:Object.keys(body),numeric_errors:Object.fromEntries(Object.entries(body).filter(([k,v])=>/error|code|status|action|login/.test(k)&&(typeof v==='number'||typeof v==='boolean'))),path:location.pathname};
      const list=command.kind==='detail'?(body.data?[body.data]:[]):(body.data?.list||[]);
      window.__plan177Rows=list;
      function fields(value,prefix='',depth=0) {
        if(!value||typeof value!=='object'||depth>4)return {};
        const out={};
        for(const [k,v] of Object.entries(value)) {
          const p=prefix?prefix+'.'+k:k;
          if(v && typeof v==='object' && !Array.isArray(v)) Object.assign(out,fields(v,p,depth+1));
          else if(/commission|price|cap|xtra|rate|start_time|end_time|update_time/.test(k) && (typeof v==='number'||typeof v==='boolean'||v===''||(typeof v==='string'&&/^-?[\d.,]+%?$/.test(v))))out[p]=v;
        }
        return out;
      }
      return {request:{kind:command.kind,params:command.params||{}},data_keys:Object.keys(body.data||{}),at:new Date().toISOString(),http:response.status,code:body.code,total_count:body.data?.total_count,page_offset:body.data?.page_offset,page_limit:body.data?.page_limit,list_len:list.length,keys:list[0]?Object.keys(list[0]):[],card_keys:list[0]?.batch_item_for_item_card_full?Object.keys(list[0].batch_item_for_item_card_full):[],rows:list.map(x=>({item_id:String(x.item_id??x.batch_item_for_item_card_full?.itemid??''),shop_id:String(x.batch_item_for_item_card_full?.shopid??''),fields:fields(x)}))};
    },command);
  });
}
try {
  const cookieSource = JSON.parse(await readFile(new URL('../../storage/db/config/shopee_affiliate_cookies.json', import.meta.url), 'utf8'));
  const context = await getContext();
  await context.addCookies(Object.entries(cookieSource).map(([name,value])=>({name,value:String(value),domain:'.shopee.vn',path:'/',secure:true})));
  for (const line of input) {
    let command;
    try { command=JSON.parse(line); }catch {process.stdout.write(JSON.stringify({error:'bad_json'})+'\n');continue;}
    if(command.kind==='close')break;
    try {const result=await probe(command); process.stdout.write(JSON.stringify({request:command,...result})+'\n'); if(result.error==='portal_login_required'||result.numeric_errors?.error===90309999)break;}
    catch(error){process.stdout.write(JSON.stringify({error:error?.name==='TimeoutError'?'timeout':'probe_failed',type:error?.name||'Error',reason:/Execution context was destroyed/.test(error?.message||'')?'navigation_interrupted':'session_or_fetch_failed'})+'\n');}
  }
} catch(error) { process.stdout.write(JSON.stringify({error:'probe_initialization_failed',type:error?.name||'Error'})+'\n'); process.exitCode=1; } finally {await closeContext();}
