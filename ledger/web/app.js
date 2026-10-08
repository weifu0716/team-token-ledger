'use strict';
const $ = id => document.getElementById(id);
let key = sessionStorage.getItem('ledger-key') || '';
let report = null;
let activeDevice = null;
const number = n => new Intl.NumberFormat('zh-TW').format(n);
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const localTime = value => value ? new Date(value).toLocaleString('zh-TW', {hour12:false}) : '從未回報';
function today() { const date = new Date(Date.now() + Number($('offset').value) * 60000); return date.toISOString().slice(0,10); }
$('day').value = today();
async function api(path, body) {
  const response = await fetch(path, {method:body === undefined ? 'GET' : 'POST', headers:{'Authorization':'Bearer '+key, ...(body===undefined?{}:{'Content-Type':'application/json'})}, ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if (!response.ok) { if(response.status===401) {sessionStorage.removeItem('ledger-key');key='';showLogin();} const error = await response.json().catch(()=>({})); throw new Error(error.error || '伺服器暫時無法回應，請稍後重試。'); }
  return response;
}
function query(){return '?day='+encodeURIComponent($('day').value)+'&offset='+encodeURIComponent($('offset').value);}
function showLogin(){ $('login').hidden=false;$('dashboard').hidden=true;$('logout').hidden=true; }
function state(d) {
  if(d.revoked) return ['已撤銷','muted'];
  if(!d.last_seen) return ['尚未回報','warning'];
  if(Date.now()-new Date(d.last_seen).getTime()>900000) return ['回報中斷','warning'];
  if(d.status.phase==='enrolling') return ['等待安裝完成','warning'];
  if(d.status.phase==='no_sources') return ['未找到使用紀錄','warning'];
  if(d.status.warnings_total || d.disputed_tokens || d.status.pending) return ['部分資料待核對','warning'];
  return ['持續回報',''];
}
function render(){
  $('login').hidden=true;$('dashboard').hidden=false;$('logout').hidden=false;
  document.querySelector('.page-heading .eyebrow').textContent=report.demo?'DEMO / 全部為合成示範資料':'DAILY OBSERVATIONS';
  $('total').textContent=number(report.total_tokens);
  const online=report.devices.filter(d=>!d.revoked&&d.last_seen&&Date.now()-new Date(d.last_seen).getTime()<=900000).length;
  $('coverage').textContent=`${online} / ${report.devices.filter(d=>!d.revoked).length} 台電腦最近 15 分鐘有回報`;
  $('updated').textContent='頁面更新：'+localTime(report.generated)+'（此裝置時間）';
  $('empty').hidden=report.devices.length>0;$('table-wrap').hidden=!report.devices.length;
  $('rows').replaceChildren();
  for(const d of report.devices){
    const tr=node('tr'); const who=node('td',d.name);who.append(node('span',d.id.slice(0,8),'subline'));tr.append(who);
    const status=node('td');const [label,cls]=state(d);status.append(node('span',label,'state '+cls),node('span',localTime(d.last_seen),'subline'));tr.append(status);
    const total=node('td',d.events?number(d.total_tokens):'—','numeric total-cell');total.append(node('span',d.events?`${number(d.input_tokens)} 輸入 / ${number(d.output_tokens)} 輸出`:'當日無可計入紀錄','subline'));tr.append(total);
    tr.append(node('td',d.events?number(d.cached_input_tokens):'—','numeric'));
    const actions=node('td');const wrap=node('div',undefined,'row-actions');const view=node('button','看工作 →','text-button');view.addEventListener('click',()=>showDetail(d.id,true));wrap.append(view);
    if(!d.revoked){const revoke=node('button','撤銷','text-button revoke');revoke.addEventListener('click',async()=>{if(!confirm(`撤銷「${d.name}」的上傳權限？現有報表會保留；恢復使用需重新配對。`))return;try{await api('/api/revoke',{id:d.id});await refresh();}catch(e){message(e.message);}});wrap.append(revoke);}
    actions.append(wrap);tr.append(actions);['員工／裝置','回報狀態','已觀測 Token','其中快取','工作與管理'].forEach((label,i)=>tr.children[i].dataset.label=label);$('rows').append(tr);
  }
  if(activeDevice) showDetail(activeDevice,false);
}
function showDetail(id,scroll){
  activeDevice=id;const d=report.devices.find(x=>x.id===id);if(!d)return;
  $('detail').hidden=false;$('detail-title').textContent=d.name+' 的工作線索';
  $('detail-note').textContent=`跨裝置重複、暫不計入：${number(d.disputed_tokens)} Token。累計解析警示：${d.status.warnings_total||0}；尚待補傳：${d.status.pending||0}。片段代表請求內容，不證明工作已完成。`;
  $('models').textContent=Object.entries(d.models).map(([m,t])=>m+' · '+number(t)).join('　／　')||'當日沒有可計入的模型用量。';
  $('tasks').replaceChildren();
  for(const t of d.tasks){const el=node('article',undefined,'task');const title=node('div',undefined,'task-title');title.append(node('span',t.project),node('span',number(t.total_tokens)+' Token'));el.append(title,node('p',t.task||'未分享工作原文；目前僅回報專案名稱。'),node('time','最後紀錄：'+localTime(t.last)));$('tasks').append(el);}
  if(!d.tasks.length)$('tasks').append(node('p','當日尚無可顯示的工作紀錄。'));
  if(scroll)$('detail').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'nearest'});
}
function message(text){$('message').textContent=text;}
async function refresh(){ if(!key)return;try{const r=await api('/api/report'+query());report=await r.json();render();message('');}catch(e){message(e.message+' 畫面保留上次成功資料，請查看更新時間。');} }
function download(blob,name){const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();key=$('key').value.trim();$('key').value='';try{const r=await api('/api/report'+query());report=await r.json();sessionStorage.setItem('ledger-key',key);render();message('');}catch(error){message(error.message);}});
$('logout').addEventListener('click',()=>{key='';report=null;sessionStorage.removeItem('ledger-key');$('rows').replaceChildren();$('tasks').replaceChildren();showLogin();});
$('refresh').addEventListener('click',refresh);$('day').addEventListener('change',refresh);$('offset').addEventListener('change',refresh);
$('detail-close').addEventListener('click',()=>{activeDevice=null;$('detail').hidden=true;});
for(const ext of ['md','csv'])$('export-'+ext).addEventListener('click',async()=>{try{const response=await api('/api/export.'+ext+query());download(await response.blob(),'team-report-'+$('day').value+'.'+ext);}catch(e){message(e.message);}});
$('add-open').addEventListener('click',()=>{$('endpoint').value=location.origin;$('pair-message').textContent='';$('pair-dialog').showModal();});
$('pair-close').addEventListener('click',()=>$('pair-dialog').close());
$('pair-form').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{const response=await api('/api/devices',{name:$('employee-name').value,endpoint:$('endpoint').value});const enrollment=await response.json();download(new Blob([JSON.stringify(enrollment,null,2)],{type:'application/json'}),'enrollment-'+enrollment.device_id+'.json');$('pair-dialog').close();$('employee-name').value='';await refresh();message('配對檔已下載。請私下交給該員工；不要上傳 GitHub。');}catch(error){$('pair-message').textContent=error.message;}finally{btn.disabled=false;}});
setInterval(()=>{if(key&&!document.hidden)refresh();},60000);
if(key)refresh();
