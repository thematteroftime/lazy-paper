// lazy-paper garden — HUD / DOM layer
// Observatory chrome (log, ledger, growth ring), paper panel, Seek overlay.
window.GardenHud = (() => {
'use strict';
const $ = id => document.getElementById(id);
const TAU = Math.PI*2;
let seekIdx = 0, seekEntries = [], seekResults = [];

// ── formatting ──────────────────────────────────────────────────────────────
const fmtInt = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g,'\u2009');
const fmtTok = n => n>=1e6 ? (n/1e6).toFixed(1)+'M' : n>=1e3 ? (n/1e3).toFixed(0)+'k' : String(n);
const fmtYM = ms => { const d=new Date(ms); return d.getFullYear()+'·'+String(d.getMonth()+1).padStart(2,'0'); };
const fmtDate = ms => { const d=new Date(ms); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); };
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const hueCss = (T,h,a) => GardenRender.SKINS[T.skin].hueStrong(h, a===undefined?1:a);

function setView(v){ document.body.dataset.view = v; }
function setCrumb(sec){
 const el = $('crumb-paper');
 el.innerHTML = '<span class="sep"> ⟩ </span><span class="here">PAPER</span>' +
  (sec ? '<span class="sep"> ⟩ </span><span class="here">§'+esc(sec.num)+' '+esc(sec.zh)+'</span>' : '');
}

// ── observatory: log + ledger + growth ring ─────────────────────────────────
function refresh(app, T){
 const d = app.data;
 const nP = d.papers.length;
 const sums = d.papers.reduce((s,p)=>{s.c+=p.n_chunks;s.e+=p.n_entities;s.t+=p.total_tokens;return s;},{c:0,e:0,t:0});
 $('led-papers').textContent = fmtInt(nP);
 $('led-chunks').textContent = fmtInt(sums.c);
 $('led-ents').textContent = fmtInt(sums.e);
 $('led-tokens').textContent = fmtTok(sums.t);
 buildLog(app, T);
 drawRing(app, T);
 buildSeekIndex(app);
}

function buildLog(app, T){
 const d = app.data, box = $('log-lines');
 box.innerHTML = '';
 if(d.papers.length < 3){
  addLine(box, '第一颗星已点亮。每一次 <i>ingest</i>,这片天空就生长一点。', null);
  return;
 }
 const fresh = d.papers.map((p,i)=>[p,i]).filter(([p])=>p.ingested_at > d.lastVisit);
 const newest = fresh.length ? fresh[fresh.length-1] : null;
 addLine(box, `+${fresh.length} 颗新星 — 点击定位`, ()=>{ if(newest) GardenApp.focusPaper(newest[0]); });
 if(newest){
  const cl = d.clusters[newest[0].cluster];
  addLine(box, `⟨ ${esc(cl.en)} ⟩ 星云扩大 · ${esc(cl.zh)}`, null, hueCss(T, cl.hue));
 }
 const freshIdx = new Set(fresh.map(([,i])=>i));
 const newLinks = d.links.filter(l=>freshIdx.has(l.a)||freshIdx.has(l.b));
 if(newLinks.length){
  const texts = [...new Set(newLinks.slice(0,3).map(l=>l.texts[0]))].join(' · ');
  addLine(box, `${newLinks.length} 条新星座线(${esc(texts)})`, null);
 }
}
function addLine(box, html, onClick, color){
 const div = document.createElement('div');
 div.className = 'log-line' + (onClick?' clickable':'');
 div.innerHTML = '<span class="log-bullet">✦</span><span>'+html+'</span>';
 if(color) div.querySelector('.log-bullet').style.color = color;
 if(onClick) div.addEventListener('click', onClick);
 box.appendChild(div);
}
function logIngest(app, p){
 const cl = app.data.clusters[p.cluster];
 const box = $('log-lines');
 const div = document.createElement('div');
 div.className = 'log-line clickable fresh';
 div.innerHTML = `<span class="log-bullet" style="color:var(--accent)">✶</span><span>刚刚 · 新星「${esc(p.title.length>20?p.title.slice(0,19)+'…':p.title)}」加入 ⟨ ${esc(cl.en)} ⟩</span>`;
 div.addEventListener('click', ()=>GardenApp.focusPaper(p));
 box.prepend(div);
 while(box.children.length>5) box.lastChild.remove();
}

// growth ring: every paper one arc segment in ingest order, thickness ∝ n_chunks
// — interactive: hover a segment to read it, click to fly to that star
let ringSegs=[], ringApp=null, ringT=null, ringHover=-1;
function drawRing(app, T){
 ringApp=app; ringT=T;
 const cv = $('ring'); const dpr = Math.min(devicePixelRatio||1,2);
 const CS = 210; cv.width = CS*dpr; cv.height = CS*dpr;
 const c = cv.getContext('2d'); c.setTransform(dpr,0,0,dpr,0,0);
 const S = GardenRender.SKINS[T.skin];
 const d = app.data;
 const papers = d.papers.slice().sort((a,b)=>a.ingested_at-b.ingested_at);
 const n = papers.length, R0 = 56, ctr = CS/2;
 const span = TAU*0.96, a0 = -Math.PI/2;
 ringSegs = papers;
 papers.forEach((p,i)=>{
  const a1 = a0 + span*i/n, a2 = a0 + span*(i+0.82)/n;
  const th = 5 + 15*Math.sqrt(Math.min(p.n_chunks,170)/170);
  const heat = GardenApp.heatOf(p);
  const hov = i===ringHover;
  c.strokeStyle = hov ? `rgba(${S.accentRGB},1)`
    : heat>0.3 ? `rgba(${S.accentRGB},0.95)` : S.hueStrong(d.clusters[p.cluster].hue, 0.85);
  c.lineWidth = hov?3.4:2.1;
  c.beginPath();
  c.arc(ctr, ctr, R0, a1, a2);
  c.stroke();
  c.beginPath();
  c.moveTo(ctr+Math.cos((a1+a2)/2)*R0, ctr+Math.sin((a1+a2)/2)*R0);
  c.lineTo(ctr+Math.cos((a1+a2)/2)*(R0+th+(hov?4:0)), ctr+Math.sin((a1+a2)/2)*(R0+th+(hov?4:0)));
  c.lineWidth = Math.max(hov?2.4:1.4, (a2-a1)*R0*0.9);
  c.stroke();
 });
 c.strokeStyle = `rgba(${S.inkRGB},0.25)`; c.lineWidth=1;
 c.beginPath(); c.arc(ctr,ctr,R0-6,0,TAU); c.stroke();
 const ae = a0 + span;
 c.fillStyle = `rgba(${S.accentRGB},1)`;
 c.beginPath(); c.arc(ctr+Math.cos(ae)*(R0-6), ctr+Math.sin(ae)*(R0-6), 2.4, 0, TAU); c.fill();
 c.fillStyle = `rgba(${S.inkRGB},0.85)`;
 c.font = '600 19px "Times New Roman","Noto Serif SC",serif';
 c.textAlign='center'; c.textBaseline='middle';
 c.fillText(n, ctr, ctr-7);
 c.font = '9.5px "IM Fell English","Times New Roman",serif';
 c.fillStyle = `rgba(${S.inkRGB},0.5)`;
 c.fillText('PAPERS', ctr, ctr+9);
 if(n>1){
  $('ring-span').textContent = fmtYM(papers[0].ingested_at)+' — 今';
 }
}
function ringIdxAt(e){
 const cv=$('ring');
 const rect=cv.getBoundingClientRect();
 const x=e.clientX-rect.left-105, y=e.clientY-rect.top-105;
 const r=Math.hypot(x,y);
 if(r<44||r>96||!ringSegs.length) return -1;
 const span=TAU*0.96, a0=-Math.PI/2;
 const delta=(Math.atan2(y,x)-a0+TAU*2)%TAU;
 if(delta>=span) return -1;
 return Math.min(ringSegs.length-1, Math.floor(delta/span*ringSegs.length));
}
function setRingHover(i, e){
 if(i===ringHover && i>=0){ return; }
 ringHover=i;
 if(ringApp) drawRing(ringApp, ringT);
 const tip=$('ring-tip');
 const cv=$('ring');
 if(i>=0){
  const p=ringSegs[i];
  const days=Math.floor((Date.now()-p.ingested_at)/864e5);
  let t=p.title; if(t.length>30)t=t.slice(0,29)+'…';
  tip.innerHTML='✶ '+esc(t)+' <em>'+(days<1?'今天':days+' 天前')+' · 点击定位</em>';
  tip.hidden=false;
  cv.style.cursor='pointer';
 }else{
  tip.hidden=true;
  cv.style.cursor='default';
 }
}

// ── paper panel ─────────────────────────────────────────────────────────────
function openPanel(app, p, T){
 const cl = app.data.clusters[p.cluster];
 const col = hueCss(T, cl.hue);
 const shared = p.entities.filter(e=>{
  const k = GardenData.norm(e.text)+'|'+e.type;
  const ent = app.data.entIndex.get(k);
  return ent && ent.papers.length>1;
 }).slice(0,5);
 $('panel-body').innerHTML = `
  <div class="pn-cluster" style="color:${col}">⟨ ${esc(cl.en)} ⟩ <span class="pn-id">${esc(p.id)}</span></div>
  <h2 class="pn-title">${esc(p.title)}</h2>
  <div class="pn-meta">${p.lang} · ${p.n_chunks} chunks · ${p.n_entities} entities · ${fmtTok(p.total_tokens)} tokens<br>ingested ${fmtDate(p.ingested_at)}</div>
  <div class="pn-kw">${p.keywords.map(k=>'<span>'+esc(k)+'</span>').join('')}</div>
  ${p.sections?`<div class="pn-sect">SECTIONS · 点击下钻 L2</div>
  <div class="pn-secs">${p.sections.map((s,k)=>{
    const w=Math.max(6,Math.round(100*s.chunks/p.n_chunks));
    return `<button class="pn-sec" data-k="${k}"><b>§${esc(s.num)}</b><span class="pn-sec-t">${esc(s.zh)} <i>${esc(s.en)}</i></span><span class="pn-sec-bar"><i style="width:${w}%"></i></span><em>${s.chunks}ch</em></button>`;
  }).join('')}</div>`:''}
  <div class="pn-sect">CRITICAL QUESTIONS</div>
  <ul class="pn-q">${p.questions.map(q=>'<li>'+esc(q)+'</li>').join('')}</ul>
  <div class="pn-sect">FIGURES</div>
  <div class="pn-figs">${p.figures.map(f=>`
    <figure class="pn-fig"><div class="pn-fig-ph"></div><figcaption>${esc(f.id)} · ${esc(f.caption)}</figcaption></figure>`).join('')}
  </div>
  ${shared.length?`<div class="pn-sect">SHARED ENTITIES — 从概念走到别的论文</div>
  <div class="pn-shared">${shared.map(e=>{
    const k = GardenData.norm(e.text)+'|'+e.type;
    const n = app.data.entIndex.get(k).papers.length;
    return `<button class="pn-ent" data-key="${esc(k)}"><i>✶</i>${esc(e.text)}<em>${n} 篇</em></button>`;
  }).join('')}</div>`:''}
  <div class="pn-actions">
    <button class="pn-btn" id="pn-open">打开 preview.html ↗</button>
    <div class="pn-hint" id="pn-open-hint" hidden>demo:无 source_run。实际产物中将打开该论文的 preview.html,或 garden 构建的 lite 阅读页。</div>
  </div>
  <div class="pn-cli">$ lazy-paper template --from ${esc(p.id)} <span># v1.15 槽位</span></div>`;
 $('panel-body').querySelectorAll('.pn-sec').forEach(b=>{
  b.addEventListener('click', ()=>GardenApp.drillSection(Number(b.dataset.k)));
 });
 $('panel-body').querySelectorAll('.pn-ent').forEach(b=>{
  b.addEventListener('click', ()=>GardenApp.locateEntity(b.dataset.key));
 });
 $('pn-open').addEventListener('click', ()=>{ $('pn-open-hint').hidden = false; });
 $('panel').classList.add('open');
}
function closePanel(){ $('panel').classList.remove('open'); }

// L2 — section detail: readable, grouped, params folded to "name = value unit"
function openSection(app, p, si, T){
 const sec = p.sections[si];
 const comp = GardenData.composeSection(p, si);
 const cl = app.data.clusters[p.cluster];
 const col = hueCss(T, cl.hue);
 const groups = {};
 comp.items.forEach(it=>{(groups[it.e.type]=groups[it.e.type]||[]).push(it);});
 const ORDER=['parameter','method','material','dopant','comparator','figure','table','claim'];
 const NAME={parameter:'PARAMETERS 参数',method:'METHODS 方法',material:'MATERIALS 材料',dopant:'DOPANTS 掺杂',comparator:'COMPARATORS 对照',figure:'FIGURES 图',table:'TABLES 表',claim:'CLAIMS 论断'};
 $('panel-body').innerHTML = `
  <button class="pn-back" id="pn-back">← 返回论文总览</button>
  <div class="pn-cluster" style="color:${col}">⟨ ${esc(cl.en)} ⟩</div>
  <h2 class="pn-title">§${esc(sec.num)} ${esc(sec.zh)} <span class="pn-title-en">${esc(sec.en)}</span></h2>
  <div class="pn-meta">${sec.chunks} chunks · ${sec.ents.length} entities<br>《${esc(p.title)}》</div>
  ${sec.q?`<div class="pn-sect">SECTION QUESTION</div><div class="pn-q-one">? ${esc(sec.q)}</div>`:''}
  ${ORDER.filter(t=>groups[t]).map(t=>`
   <div class="pn-etype">${NAME[t]||esc(t).toUpperCase()}</div>
   ${groups[t].map(it=>{
     const k = GardenData.norm(it.e.text)+'|'+it.e.type;
     const rec = app.data.entIndex.get(k);
     const sh = rec && rec.papers.length>1;
     return `<div class="pn-erow${sh?' shared':''}"${sh?` data-key="${esc(k)}"`:''}><span class="gl">${sh?'✶':'·'}</span><span>${esc(it.label)}</span>${sh?`<em>${rec.papers.length} 篇</em>`:''}</div>`;
   }).join('')}`).join('')}
  ${comp.hidden?`<div class="pn-meta" style="margin-top:10px">+${comp.hidden} more entities</div>`:''}`;
 $('pn-back').addEventListener('click', ()=>GardenApp.undrill());
 $('panel-body').querySelectorAll('.pn-erow.shared').forEach(r=>{
  r.addEventListener('click', ()=>GardenApp.locateEntity(r.dataset.key));
 });
 $('panel').classList.add('open');
}

// ── highlight chip ──────────────────────────────────────────────────────────
function showHl(e){
 $('hl-chip').innerHTML = `<i>✶</i> ${esc(e.text)} <span>· ${esc(e.type)} · ${e.papers.length} 篇共享</span><button id="hl-x">✕</button>`;
 $('hl-chip').classList.add('on');
 $('hl-x').addEventListener('click', ()=>GardenApp.clearHl());
}
function hideHl(){ $('hl-chip').classList.remove('on'); }

// ── Seek (⌘K) — static navigation search (§2.4) ─────────────────────────────
function buildSeekIndex(app){
 seekEntries = [];
 app.data.papers.forEach((p,i)=>{
  seekEntries.push({kind:'paper', label:p.title, sub:p.keywords.join(' · '), p,
   hay:(p.title+' '+p.keywords.join(' ')).toLowerCase()});
 });
 app.data.entIndex.forEach(ent=>{
  if(ent.type==='value'||ent.type==='unit'||ent.type==='figure'||ent.type==='table') return;
  seekEntries.push({kind:ent.type, label:ent.text, sub:ent.papers.length+' 篇', key:ent.key,
   hay:ent.text.toLowerCase()});
 });
}
function seekOpen(){ return $('seek').classList.contains('open'); }
function toggleSeek(force){
 const on = force!==undefined ? force : !seekOpen();
 $('seek').classList.toggle('open', on);
 if(on){ $('seek-in').value=''; $('seek-in').focus(); runSeek(''); }
}
function runSeek(q){
 q = q.trim().toLowerCase();
 const res = [];
 if(q){
  for(const e of seekEntries){
   const s = fuzzyScore(q, e.hay);
   if(s===null) continue;
   res.push([e, s + (e.kind==='paper'?8:0)]);
  }
  res.sort((a,b)=>b[1]-a[1]);
 } else {
  const ps = seekEntries.filter(e=>e.kind==='paper').slice(-5).reverse();
  ps.forEach(e=>res.push([e,0]));
 }
 seekResults = res.slice(0,9).map(r=>r[0]);
 seekIdx = 0;
 renderSeek();
}
// fuzzy: substring scores high; otherwise in-order subsequence with gap penalty
function fuzzyScore(q, h){
 const ix = h.indexOf(q);
 if(ix>=0) return 100 - Math.min(ix,50);
 let last=-1, gaps=0, bonus=0;
 for(const ch of q){
  if(ch===' ') continue;
  const j = h.indexOf(ch, last+1);
  if(j<0) return null;
  if(last>=0) gaps += j-last-1;
  if(j===0 || h[j-1]===' ' || h[j-1]==='-') bonus += 5;
  last = j;
 }
 return 40 + bonus - Math.min(gaps*1.5, 45);
}
function renderSeek(){
 $('seek-results').innerHTML = seekResults.map((e,i)=>`
  <div class="sk-row${i===seekIdx?' sel':''}" data-i="${i}">
   <span class="sk-kind">${e.kind==='paper'?'论文':esc(e.kind)}</span>
   <span class="sk-label">${esc(e.label)}</span>
   <span class="sk-sub">${esc(e.sub)}</span>
   <span class="sk-go">定位 ↵</span>
  </div>`).join('') || '<div class="sk-empty">没有条目。试试 keywords、实体、作者。</div>';
 $('seek-results').querySelectorAll('.sk-row').forEach(r=>{
  r.addEventListener('click', ()=>goSeek(Number(r.dataset.i)));
  r.addEventListener('mousemove', ()=>{ seekIdx=Number(r.dataset.i); markSel(); });
 });
}
function markSel(){
 $('seek-results').querySelectorAll('.sk-row').forEach((r,i)=>r.classList.toggle('sel', i===seekIdx));
}
function goSeek(i){
 const e = seekResults[i];
 if(!e) return;
 toggleSeek(false);
 if(e.kind==='paper') GardenApp.focusPaper(e.p);
 else GardenApp.locateEntity(e.key);
}

// ── field manual ─────────────────────────────────────────────
function manualOpen(){ return $('manual').classList.contains('open'); }
function toggleManual(force){
 const on = force!==undefined ? force : !manualOpen();
 $('manual').classList.toggle('open', on);
}

// ── boot wiring ─────────────────────────────────────────────────────────────
function init(){
 $('btn-ingest').addEventListener('click', ()=>GardenApp.ingest());
 $('crumb-obs').addEventListener('click', ()=>GardenApp.toObs());
 $('panel-x').addEventListener('click', ()=>GardenApp.exitFocus());
 $('btn-seek').addEventListener('click', ()=>toggleSeek(true));
 // collapsible observation log (persisted)
 const foldKey='garden-log-collapsed';
 const setFold=(on)=>{
  $('obs-log').classList.toggle('collapsed', on);
  $('log-fold').textContent = on ? '⌃' : '⌄';
  $('log-fold').title = on ? '展开日志' : '折叠日志';
  try{ localStorage.setItem(foldKey, on?'1':'0'); }catch(e){}
 };
 $('log-fold').addEventListener('click', ()=>setFold(!$('obs-log').classList.contains('collapsed')));
 try{ if(localStorage.getItem(foldKey)==='1') setFold(true); }catch(e){}
 const ringCv = $('ring');
 ringCv.addEventListener('pointermove', e=>setRingHover(ringIdxAt(e), e));
 ringCv.addEventListener('pointerleave', ()=>setRingHover(-1));
 ringCv.addEventListener('click', e=>{
  const i=ringIdxAt(e);
  if(i>=0) GardenApp.focusPaper(ringSegs[i]);
 });
 $('btn-manual').addEventListener('click', ()=>toggleManual(true));
 $('btn-manual-obs').addEventListener('click', ()=>toggleManual(true));
 $('manual-x').addEventListener('click', ()=>toggleManual(false));
 $('manual').addEventListener('pointerdown', e=>{ if(e.target.id==='manual') toggleManual(false); });
 $('enter-hint').addEventListener('click', ()=>{
  const a = GardenApp.app; a.cam.tz = a.zFit*1.6;
  GardenApp.app.view='atlas'; setView('atlas');
 });
 $('seek-in').addEventListener('input', e=>runSeek(e.target.value));
 $('seek-in').addEventListener('keydown', e=>{
  if(e.key==='ArrowDown'){ e.preventDefault(); seekIdx=Math.min(seekIdx+1,seekResults.length-1); markSel(); }
  else if(e.key==='ArrowUp'){ e.preventDefault(); seekIdx=Math.max(seekIdx-1,0); markSel(); }
  else if(e.key==='Enter'){ goSeek(seekIdx); }
 });
 $('seek').addEventListener('pointerdown', e=>{ if(e.target.id==='seek') toggleSeek(false); });
}

return {init, setView, setCrumb, refresh, openPanel, openSection, closePanel, logIngest,
  showHl, hideHl, seekOpen, toggleSeek, manualOpen, toggleManual, drawRing};
})();
