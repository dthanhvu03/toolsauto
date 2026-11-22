/** PLAN-177 handoff smoke: artifacts only, one backend, bounded calls, always close. */
import {readFile,writeFile} from 'node:fs/promises';
import {writeFileSync} from 'node:fs';
import {performance} from 'node:perf_hooks';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {loadBackend} from '../../scripts/shopee_bridge/index.mjs';
import {bridgeConfig,createBridgeServer} from '../../scripts/shopee_bridge/server.mjs';
const exec=promisify(execFile);
const proofFile=new URL('repo-native-handoff-smoke-20261119.json',import.meta.url);
const proof={at:new Date().toISOString(),handoff:'.comms/handoffs/cursor-to-ag/TASK-plan177-repo-bridge-native-smoke.md',mode:'smoke_only_no_customer_activation',calls:[],stages:[],upstream_errors:[],auth_blocked:false,same_backend_instance:true};
let backend,bridge;
const started=performance.now();
const workDeadline=started+70000;
function persist(){writeFileSync(proofFile,JSON.stringify(proof,null,2)+'\n');}
function remaining(maximum){return Math.max(0,Math.min(maximum,workDeadline-performance.now()));}
function processBudget(cap){const ms=Math.floor(remaining(cap));if(ms<1)throw Object.assign(new Error('budget'),{code:'timeout'});return ms;}
function safeCode(error){return ['auth_required','timeout','identity_mismatch','missing_split_or_cap','unavailable_product','invalid_price','invalid_period','session_unavailable','session_or_transport_error','upstream_error','shortlink_failed'].includes(error?.code)?error.code:'smoke_step_error';}
function failure(error){return error?.name==='TimeoutError'||error?.name==='AbortError'?'timeout':safeCode(error);}
function observe(method){return async(...args)=>{try{return await backend[method](...args);}catch(error){const code=safeCode(error);proof.upstream_errors.push({operation:method,code});if(code==='auth_required')proof.auth_blocked=true;persist();throw error;}};}
const hard=setTimeout(()=>{proof.error='hard_smoke_timeout';proof.cleanup={closed:false,reason:'hard_stop_outer_shell_restores_legacy'};persist();process.exit(2);},90000);
async function nativeQuote(shop,item){
 const py=`import json,time
from datetime import datetime,timezone
from cashback_bot.native_shopee_quote import NativeShopeeQuoteClient,NativeQuoteError
from cashback_bot.shopee_url import ShopeeTarget
shop=${shop}
item=${item}
start=time.monotonic()
try:
 q=NativeShopeeQuoteClient().fetch_quote(ShopeeTarget(f'https://shopee.vn/product/{shop}/{item}',item,shop,None),now=datetime.now(timezone.utc),deadline=start+9)
 print(json.dumps({'kind':'native_quote','item_id':item,'shop_id':shop,'ids_exact':q.item_id==item and q.shop_id==shop,'source':q.data_source,'price_vnd':q.price_vnd,'sure_commission_vnd':q.sure_commission_vnd,'seller_commission_vnd':q.seller_commission_vnd,'shopee_commission_vnd':q.shopee_commission_vnd,'is_xtra':q.is_xtra,'price_basis':q.price_basis,'last_update':q.last_update,'fetched_at':q.fetched_at.isoformat(),'elapsed_sec':round(time.monotonic()-start,3)}))
except NativeQuoteError as e:
 print(json.dumps({'kind':'native_quote','item_id':item,'error':e.code,'elapsed_sec':round(time.monotonic()-start,3)}))
except Exception as e:
 print(json.dumps({'kind':'native_quote','item_id':item,'error':'client_step_error','type':type(e).__name__}))
`;
 let stdout='';
 try{({stdout}=await exec('wsl.exe',['-d','Ubuntu','--cd','/home/vu/toolsauto','.venv/bin/python','-c',py],{timeout:processBudget(13000),maxBuffer:32768,windowsHide:true}));}
 catch(e){stdout=typeof e.stdout==='string'?e.stdout:'';}
 const row=stdout.split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line);}catch{return null;}}).find(x=>x?.kind==='native_quote');
 const data=row||{kind:'native_quote',item_id:item,error:'client_process_failed'};
 proof.calls.push(data);persist();return data;
}
try{
 const config=bridgeConfig();
 const localHost=config.host==='0.0.0.0'?'127.0.0.1':config.host.includes(':')?'['+config.host+']':config.host;
 const baseUrl='http://'+localHost+':'+config.port;
 backend=await loadBackend(process.env,{diagnostics:e=>{if(proof.stages.length<150)proof.stages.push(e);persist();}});
 const prepareStart=performance.now();await backend.prepare(45000);
 proof.preparation={ready:backend.ready,elapsed_sec:Math.round(performance.now()-prepareStart)/1000};persist();
 const observed={quote:observe('quote'),shortlink:observe('shortlink'),vouchers:observe('vouchers'),close:()=>backend.close()};
 bridge=createBridgeServer({backend:observed,allowedPeers:config.allowedPeers});
 await new Promise((resolve,reject)=>{bridge.server.once('error',reject);bridge.server.listen(config.port,config.host,resolve);});
 const h=await fetch(baseUrl+'/health',{signal:AbortSignal.timeout(3000)});const hb=await h.json();
 proof.repo_health={http:h.status,implementation:hb.implementation,quote_schema:hb.quote_schema};
 const wslHealth=await exec('wsl.exe',['-d','Ubuntu','--cd','/home/vu/toolsauto','.venv/bin/python','-c',`import json,requests
from cashback_bot.shopee_shortener import get_bridge_url
r=requests.get(get_bridge_url()+'/health',timeout=3)
b=r.json()
print(json.dumps({'http':r.status_code,'implementation':b.get('implementation')}))`],{timeout:processBudget(6000),windowsHide:true,maxBuffer:4096});
 proof.wsl_repo_health=JSON.parse(wslHealth.stdout.trim());persist();
 const q=await nativeQuote(1175585681,54321049804);
 if(q.error||!q.ids_exact||proof.auth_blocked){proof.result='failed_native_quote';}
 else{
  if(remaining(6500)<6500)throw Object.assign(new Error('budget'),{code:'timeout'});
  const shortStart=performance.now();
  const r=await fetch(baseUrl+'/api/generate_shortlink?'+new URLSearchParams({url:'https://shopee.vn/product/1175585681/54321049804',sub_id:'PLAN177HANDOFFSMOKE',timeout_ms:'6000'}),{signal:AbortSignal.timeout(6500)});
  const b=await r.json();const host=typeof b.short_link==='string'?new URL(b.short_link).hostname:null;
  const short={kind:'repo_shortlink',http:r.status,success:b.success===true,host,error:b.error||null,elapsed_sec:Math.round(performance.now()-shortStart)/1000};proof.calls.push(short);persist();
  proof.result=short.success&&host==='s.shopee.vn'?'passed_required_steps':'failed_repo_shortlink';
  if(proof.result==='passed_required_steps'&&!proof.auth_blocked&&remaining(16000)>=16000){await nativeQuote(344893921,48720020072);}
 }
}catch(error){proof.error=failure(error);proof.result??='failed_before_required_completion';persist();}
finally{
 try{if(bridge)await bridge.close();else if(backend)await backend.close();proof.cleanup={closed:true};}
 catch(error){proof.cleanup={closed:false,code:failure(error)};}
 finally{proof.total_elapsed_sec=Math.round(performance.now()-started)/1000;persist();clearTimeout(hard);await writeFile(proofFile,JSON.stringify(proof,null,2)+'\n');process.stdout.write(JSON.stringify({result:proof.result,error:proof.error,preparation:proof.preparation,repo_health:proof.repo_health,wsl_repo_health:proof.wsl_repo_health,calls:proof.calls,auth_blocked:proof.auth_blocked,cleanup:proof.cleanup,total_elapsed_sec:proof.total_elapsed_sec})+'\n');}
}
