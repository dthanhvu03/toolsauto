/** Authorized Gate B smoke. Stop legacy bridge before run; shell restores it in finally. */
import { writeFileSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { loadBackend } from '../../scripts/shopee_bridge/index.mjs';
import { bridgeConfig, createBridgeServer } from '../../scripts/shopee_bridge/server.mjs';
const exec = promisify(execFile);
const root = new URL('../../', import.meta.url);
const output = new URL('phase2-live-proof.json', import.meta.url);
const stageFile=new URL('phase2-live-stages.json',import.meta.url);
const proof = {at:new Date().toISOString(),mode:'bounded_poc_not_production_deploy',calls:[],stages:[]};
let bridge, backend, hardStop;
try {
  const config=bridgeConfig();
  backend=await loadBackend(process.env,{diagnostics:event=>{proof.stages.push(event);writeFileSync(stageFile,JSON.stringify(proof,null,2));}});
  hardStop=setTimeout(()=>{proof.error='hard_smoke_timeout';writeFileSync(output,JSON.stringify(proof,null,2));process.exit(2);},90000);
  const prep=performance.now();
  await backend.prepare(45000);
  proof.preparation={ready:backend.ready,elapsed_sec:Math.round(performance.now()-prep)/1000};
  bridge=createBridgeServer({backend,allowedPeers:config.allowedPeers});
  await new Promise((resolve,reject)=>{bridge.server.once('error',reject);bridge.server.listen(config.port,config.host,resolve);});
  const health=await fetch('http://127.0.0.1:'+config.port+'/health',{signal:AbortSignal.timeout(3000)});
  proof.health={http:health.status,implementation:(await health.json()).implementation};
  const py = `import json,time
from datetime import datetime,timezone
import requests
from cashback_bot.shopee_shortener import get_bridge_url
from cashback_bot.native_shopee_quote import NativeShopeeQuoteClient,NativeQuoteError
from cashback_bot.shopee_url import ShopeeTarget
h=requests.get(get_bridge_url()+'/health',timeout=3)
print(json.dumps({'wsl_health_http':h.status_code}))
for shop,item in [(1175585681,54321049804),(344893921,48720020072)]:
 start=time.monotonic()
 try:
  q=NativeShopeeQuoteClient().fetch_quote(ShopeeTarget(f'https://shopee.vn/product/{shop}/{item}',item,shop,None),now=datetime.now(timezone.utc),deadline=start+19)
  print(json.dumps({'kind':'native_python_client','item_id':item,'ids_exact':q.shop_id==shop and q.item_id==item,'price_vnd':q.price_vnd,'sure_commission_vnd':q.sure_commission_vnd,'seller_commission_vnd':q.seller_commission_vnd,'shopee_commission_vnd':q.shopee_commission_vnd,'is_xtra':q.is_xtra,'source':q.data_source,'last_update':q.last_update,'price_basis':q.price_basis,'elapsed_sec':round(time.monotonic()-start,3)}))
 except NativeQuoteError as exc:
  print(json.dumps({'kind':'native_python_client','item_id':item,'error':exc.code,'elapsed_sec':round(time.monotonic()-start,3)}))
`;
  const pyResult=await exec('wsl.exe',['-d','Ubuntu','--cd','/home/vu/toolsauto','.venv/bin/python','-c',py],{timeout:45000,windowsHide:true,maxBuffer:65536});
  proof.calls.push(...pyResult.stdout.trim().split(/\r?\n/).filter(Boolean).map(line=>JSON.parse(line)));
  const start=performance.now();
  const short=await fetch('http://127.0.0.1:'+config.port+'/api/generate_shortlink?'+new URLSearchParams({url:'https://shopee.vn/product/1175585681/54321049804',sub_id:'PLAN177PHASE2SMOKE',timeout_ms:'18000'}),{signal:AbortSignal.timeout(19000)});
  const body=await short.json();
  proof.calls.push({kind:'shortlink',http:short.status,success:body.success,host:body.short_link?new URL(body.short_link).hostname:null,error:body.error||null,elapsed_sec:Math.round(performance.now()-start)/1000});
} catch(error) {
  proof.error=error.name==='TimeoutError'?'smoke_timeout':(['timeout','auth_required','session_or_transport_error','missing_split_or_cap','unavailable_product'].includes(error.code)?error.code:'smoke_failed');
} finally {
  if(bridge)await bridge.close(); else if(backend)await backend.close();
  proof.closed=true;
  await writeFile(output,JSON.stringify(proof,null,2)+'\n');
  clearTimeout(hardStop);
  process.stdout.write(JSON.stringify(proof)+'\n');
}
