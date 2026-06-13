// lazy-paper garden — app: camera state machine + scene composition + input
// Zoom stops on one continuous camera (§2):
//   Observatory → Atlas L0 → L1 paper (section constellation) → L2 section ring.
window.GardenApp = (() => {
'use strict';
const R = () => window.GardenRender;
const TAU = Math.PI*2;
const clamp = (v,a,b)=>v<a?a:v>b?b:v;
const easeIO = t => t<0.5 ? 2*t*t : 1-Math.pow(-2*t+2,2)/2;
const backOut = t => 1 + 2.7*Math.pow(t-1,3) + 1.7*Math.pow(t-1,2);
const SERIF = '"Times New Roman","Noto Serif SC",serif';
const BRUSH = '"Ma Shan Zheng","Noto Serif SC",serif';
const FELL = '"IM Fell English","Times New Roman",serif';
// Ma Shan Zheng is a CJK calligraphy face with no real Latin glyphs — using it
// on English text renders muddy/abstract. Only reach for it when the label is
// actually Chinese; otherwise serif keeps it legible.
const cjk = s => /[一-鿿]/.test(s || '');
const labelFont = s => cjk(s) ? BRUSH : SERIF;

const T = { skin:'paper', paperCount:60, clusterCount:5, coolingDays:7,
            spikeForm:'cross', linkBudget:50, nebula:60, zoomDur:0.9, drift:1 };

let app = null;

// ── helpers ─────────────────────────────────────────────────────────────────
const heatOf = p => Math.exp(-((Date.now()-p.ingested_at)/864e5)/T.coolingDays);
function densF(){ // density attenuation — big libraries get slimmer stars
 const n = app && app.data ? app.data.papers.length : 60;
 return clamp(Math.sqrt(75/Math.max(n,20)), 0.62, 1.08);
}
function starR(p, z){
 return (2.3 + 5.2*Math.sqrt(Math.min(p.n_chunks,170)/170)) * (0.68+0.5*clamp(z,0.6,2.4)) * densF();
}
function w2s(wx, wy){
 const c = app.cam;
 return [(wx-c.x)*c.z + app.vw/2, (wy-c.y)*c.z + app.vh/2];
}

// ── lifecycle ───────────────────────────────────────────────────────────────
function init(){
 const canvas = document.getElementById('sky');
 app = { canvas, ctx: canvas.getContext('2d'), vw:0, vh:0, dpr:1,
   cam:{x:0,y:0,z:0.5,tx:0,ty:0,tz:0.5}, view:'obs', zFit:0.6,
   focus:null, hl:null, hover:null, anims:[], _stars:[], _ents:[], _secs:[], _grid:new Map(),
   data:null, visLinks:[], labelSet:new Set(), layer:null, focusLinks:[],
   dust:null, pings:[], linksByStar:new Map(),
   lastT: performance.now(), drag:null, mx:0, my:0 };
 app.dust = R().buildDust();
 app.sky = { meteors:[], comet:null, nextMeteor:4, nextComet:16,
   walker:{x:0,y:0,tx:0,ty:0,steps:[],trav:0,side:1,init:false} };
 app._lastDrawT = 0;
 resize();
 window.addEventListener('resize', resize);
 regen(true);
 bindInput();
 document.body.dataset.skin = T.skin;
 requestAnimationFrame(loop);
 return app;
}

function resize(){
 const c = app.canvas;
 app.vw = window.innerWidth; app.vh = window.innerHeight;
 app.dpr = Math.min(window.devicePixelRatio||1, 2);
 c.width = app.vw*app.dpr; c.height = app.vh*app.dpr;
 c.style.width = app.vw+'px'; c.style.height = app.vh+'px';
 computeFit();
}
function computeFit(){
 if(!app.data) return;
 let mr = 100;
 for(const p of app.data.papers) mr = Math.max(mr, Math.hypot(p.x,p.y)+90);
 app.zFit = (Math.min(app.vw,app.vh)/2 - 60) / mr;
 if (app.view==='obs'){ app.cam.tz = app.zFit*0.97; }
}

function regen(first){
 app.data = window.GARDEN_EXPORT
   ? GardenData.adapt(window.GARDEN_EXPORT)
   : GardenData.generate({papers:T.paperCount, clusters:T.clusterCount, seed:7});
 app.focus = null; app.hl = null; app.anims = [];
 refreshDerived();
 computeFit();
 if (first || app.view==='obs') toObs(true);
 else { app.view='atlas'; GardenHud.setView('atlas'); GardenHud.closePanel(); }
 GardenHud.refresh(app, T);
}
function refreshDerived(){
 app.visLinks = GardenData.applyBudget(app.data.links, T.linkBudget);
 rebuildLinkIndex();
 app.layer = R().buildLayer(app.data, T);
 for(const cl of app.data.clusters){
  const pts = app.data.papers.filter(p=>p.cluster===cl.idx);
  if(!pts.length) continue;
  let cx=0, minY=1e9;
  pts.forEach(p=>{cx+=p.x; minY=Math.min(minY,p.y);});
  cl.labelX = cx/pts.length; cl.labelY = minY - 46;
 }
 const budget = Math.max(4, 25 - app.data.clusters.length - 2);
 app.labelSet = new Set(app.data.papers.map((p,i)=>[i,p.n_chunks])
   .sort((a,b)=>b[1]-a[1]).slice(0,budget).map(x=>x[0]));
}

function rebuildLinkIndex(){
 app.linksByStar = new Map();
 for(const l of app.visLinks){
  if(!app.linksByStar.has(l.a)) app.linksByStar.set(l.a,[]);
  if(!app.linksByStar.has(l.b)) app.linksByStar.set(l.b,[]);
  app.linksByStar.get(l.a).push(l); app.linksByStar.get(l.b).push(l);
 }
}

// ── view transitions ────────────────────────────────────────────────────────
function toObs(snap){
 app.view='obs'; app.hl=null;
 if(app.focus){ app.focus.dir=-1; GardenHud.closePanel(); GardenHud.setCrumb(null); }
 app.cam.tx=0; app.cam.ty=0; app.cam.tz=app.zFit*0.97;
 if(snap){ app.cam.x=0; app.cam.y=0; app.cam.z=app.zFit*0.97; }
 GardenHud.setView('obs');
}
function toAtlas(z){
 app.view='atlas';
 if(app.focus){ app.focus.dir=-1; GardenHud.closePanel(); GardenHud.setCrumb(null); }
 if(z) app.cam.tz=z;
 GardenHud.setView('atlas');
}
function layoutFocus(p){
 const n = p.sections ? p.sections.length : 0;
 const secs = (p.sections||[]).map((s,k)=>({
  s, k, ang: -Math.PI/2 + TAU/(n*2) + k*TAU/Math.max(n,1) }));
 const shared=[];
 const seen=new Set();
 for(const e of p.entities){
  if(e.type==='value'||e.type==='unit'||e.type==='author')continue;
  const key=GardenData.norm(e.text)+'|'+e.type;
  if(seen.has(key))continue; seen.add(key);
  const rec=app.data.entIndex.get(key);
  if(rec&&rec.papers.length>1) shared.push({e,key,n:rec.papers.length});
 }
 shared.sort((a,b)=>b.n-a.n);
 const sh=shared.slice(0,6);
 sh.forEach((o,j)=>{o.ang=-Math.PI/2+j*TAU/sh.length;});
 const claim=p.entities.find(e=>e.type==='claim');
 return {secs, shared:sh, claim};
}
function focusPaper(p){
 const i = app.data.papers.indexOf(p);
 app.view='focus'; app.hl=null;
 const zT = 2.35;
 app.focus = { p, i, t: app.focus&&app.focus.p===p ? app.focus.t : 0, dir:1,
   level:1, sec:null, secT:0, items:null, layout: layoutFocus(p) };
 app.focusLinks = app.data.links.filter(l=>l.a===i||l.b===i).slice(0,8);
 app.cam.tx = p.x + 170/zT;  // shift left to clear the paper panel
 app.cam.ty = p.y; app.cam.tz = zT;
 GardenHud.setView('focus');
 GardenHud.setCrumb(null);
 GardenHud.openPanel(app, p, T);
}
function drillSection(k){
 const F = app.focus;
 if(!F || !F.p.sections || !F.p.sections[k]) return;
 F.sec = k; F.level = 2;
 const comp = GardenData.composeSection(F.p, k);
 F.items = comp.items; F.itemsHidden = comp.hidden;
 const zT = 3.05;
 app.cam.tz = zT; app.cam.tx = F.p.x + 170/zT; app.cam.ty = F.p.y;
 GardenHud.setCrumb(F.p.sections[k]);
 GardenHud.openSection(app, F.p, k, T);
}
function undrill(){
 const F = app.focus;
 if(!F) return;
 F.level = 1;
 const zT = 2.35;
 app.cam.tz = zT; app.cam.tx = F.p.x + 170/zT; app.cam.ty = F.p.y;
 GardenHud.setCrumb(null);
 GardenHud.openPanel(app, F.p, T);
}
function exitFocus(){
 if(!app.focus) return;
 app.focus.dir = -1; app.focus.level = 1;
 app.view='atlas';
 app.cam.tz = Math.min(app.cam.tz, 1.45);
 app.cam.tx = app.focus.p.x; app.cam.ty = app.focus.p.y;
 GardenHud.setView('atlas');
 GardenHud.setCrumb(null);
 GardenHud.closePanel();
}
function setHl(key){
 const e = app.data.entIndex.get(key);
 if(!e || e.papers.length<2){ return false; }
 app.hl = e;
 GardenHud.showHl(e);
 return true;
}
function clearHl(){ app.hl=null; GardenHud.hideHl(); }
function locateEntity(key){
 const e = app.data.entIndex.get(key);
 if(!e) return;
 app.hl = e; GardenHud.showHl(e);
 if(app.focus){ exitFocus(); }
 let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
 e.papers.forEach(pi=>{const p=app.data.papers[pi];
  x0=Math.min(x0,p.x);y0=Math.min(y0,p.y);x1=Math.max(x1,p.x);y1=Math.max(y1,p.y);});
 const cx=(x0+x1)/2, cy=(y0+y1)/2;
 const span=Math.max(x1-x0, y1-y0, 160)+160;
 app.view='atlas'; GardenHud.setView('atlas');
 app.cam.tx=cx; app.cam.ty=cy;
 app.cam.tz=clamp(Math.min(app.vw,app.vh)/span, app.zFit*1.1, 2.2);
}
function ingest(){
 const p = GardenData.ingestOne(app.data);
 refreshDerived(); computeFit();
 app.anims.push({i: app.data.papers.length-1, t0: performance.now()});
 if(app.view==='focus') exitFocus();
 GardenHud.refresh(app, T);
 GardenHud.logIngest(app, p);
 return p;
}

// ── tweaks ──────────────────────────────────────────────────────────────────
function applyTweaks(t){
 const prev = Object.assign({}, T);
 Object.assign(T, t);
 if(!app) return;
 if(T.skin!==prev.skin){ document.body.dataset.skin=T.skin; app.layer=R().buildLayer(app.data,T); GardenHud.refresh(app,T); }
 if(T.paperCount!==prev.paperCount || T.clusterCount!==prev.clusterCount){ regen(); return; }
 if(T.linkBudget!==prev.linkBudget){ app.visLinks = GardenData.applyBudget(app.data.links, T.linkBudget); rebuildLinkIndex(); }
 if(T.nebula!==prev.nebula) app.layer = R().buildLayer(app.data, T);
}

// ── frame loop ──────────────────────────────────────────────────────────────
function loop(ts){
 const dt = Math.min((ts-app.lastT)/1000, 0.05); app.lastT = ts;
 const c = app.cam;
 const k = 1 - Math.exp(-dt*3.4/Math.max(T.zoomDur,0.2));
 c.x += (c.tx-c.x)*k; c.y += (c.ty-c.y)*k; c.z += (c.tz-c.z)*k;
 if(app.focus){
  app.focus.t = clamp(app.focus.t + dt/0.55*app.focus.dir, 0, 1);
  const d2 = app.focus.level===2 ? 1 : -1;
  app.focus.secT = clamp(app.focus.secT + dt/0.5*d2, 0, 1);
  if(app.focus.dir<0 && app.focus.t<=0) app.focus=null;
 }
 draw(ts/1000);
 requestAnimationFrame(loop);
}

function draw(time){
 const {ctx, vw, vh, cam, data} = app;
 const S = R().SKINS[T.skin];
 ctx.setTransform(app.dpr,0,0,app.dpr,0,0);
 ctx.fillStyle = S.bg; ctx.fillRect(0,0,vw,vh);
 drawDust(ctx, S, time, false);          // far + mid parallax fields
 const [lx,ly] = w2s(-820,-820);
 ctx.globalAlpha = 0.97 + 0.03*Math.sin(time*0.35);   // nebula breathing
 ctx.drawImage(app.layer, lx, ly, 1640*cam.z, 1640*cam.z);
 ctx.globalAlpha = 1;
 const f = app.focus ? easeIO(app.focus.t) : 0;
 const dim = 1 - 0.78*f;
 const fi = app.focus ? app.focus.i : -1;

 // celestial drift — every star rides a slow seeded epicycle (流动感)
 const NP = data.papers.length;
 if(!app._wx || app._wx.length < NP){
  app._wx = new Float64Array(Math.max(NP,256));
  app._wy = new Float64Array(Math.max(NP,256));
 }
 const dr = T.drift;
 // differential cluster pendulums + two-harmonic epicycles — 灵动不散架
 // (speeds tuned so motion is visible within a few seconds of watching)
 const rotC = data.clusters.map(cl=>{
  const th = 0.055*dr*Math.sin(time*(0.07+cl.idx*0.018)+cl.idx*2.1);
  return [Math.cos(th),Math.sin(th),cl.cx||0,cl.cy||0];
 });
 for(let i=0;i<NP;i++){
  const p=data.papers[i], s=p.seed;
  const rc=rotC[p.cluster]||[1,0,0,0];
  const ox=p.x-rc[2], oy=p.y-rc[3];
  let wx=rc[2]+ox*rc[0]-oy*rc[1];
  let wy=rc[3]+ox*rc[1]+oy*rc[0];
  const A=(2.2+(s%23)*0.17)*dr;
  const w1=0.22+(s%13)*0.045, w2b=0.5+(s%7)*0.09;
  const ph=(s%628)/100;
  wx+=Math.cos(time*w1+ph)*A+Math.cos(time*w2b+ph*2.3)*A*0.35;
  wy+=Math.sin(time*w1*0.83+ph*1.7)*A+Math.sin(time*w2b*0.9+ph*0.7)*A*0.35;
  app._wx[i]=wx; app._wy[i]=wy;
 }

 // L0 constellation lines — hover a star to light up its edges and see WHY
 const hovStar = (!app.focus && app.hover && app.hover.kind==='star') ? app.hover.i : -1;
 let neighbor = null;
 if(hovStar>=0){
  neighbor = new Set([hovStar]);
  (app.linksByStar.get(hovStar)||[]).forEach(l=>{neighbor.add(l.a);neighbor.add(l.b);});
 }
 ctx.lineWidth = 1;
 const edgeLabels=[];
 for(const l of app.visLinks){
  if(l.a===fi || l.b===fi) continue;
  const pa=data.papers[l.a], pb=data.papers[l.b];
  const [ax,ay]=w2s(app._wx[l.a],app._wy[l.a]), [bx,by]=w2s(app._wx[l.b],app._wy[l.b]);
  if((ax<-80&&bx<-80)||(ax>vw+80&&bx>vw+80)||(ay<-80&&by<-80)||(ay>vh+80&&by>vh+80)) continue;
  const mx=(ax+bx)/2, my=(ay+by)/2;
  const dx=bx-ax, dy=by-ay, dl=Math.hypot(dx,dy)||1;
  const sgn = (l.a*31+l.b)%2 ? 1 : -1;
  const und = 0.07*(1+0.18*Math.sin(time*0.45+(l.a+l.b)));   // gentle undulation
  const cpx = mx - dy/dl*dl*und*sgn, cpy = my + dx/dl*dl*und*sgn;
  const hot = hovStar>=0 && (l.a===hovStar||l.b===hovStar);
  const base = (0.16+0.16*Math.min(l.w/4,1))*dim;
  ctx.strokeStyle = hot ? `rgba(${S.accentRGB},${0.8*dim})`
    : `rgba(${S.inkRGB},${neighbor?base*0.28:base})`;
  ctx.lineWidth = hot?1.4:1;
  if(S.mode==='paper'){ ctx.setLineDash([2,6]); ctx.lineCap='round'; }
  ctx.beginPath(); ctx.moveTo(ax,ay);
  ctx.quadraticCurveTo(cpx, cpy, bx, by);
  ctx.stroke();
  if(S.mode==='paper'){ ctx.setLineDash([]); ctx.lineCap='butt'; }
  if(hot) edgeLabels.push([0.25*ax+0.5*cpx+0.25*bx, 0.25*ay+0.5*cpy+0.25*by, l]);
 }
 ctx.lineWidth = 1;
 // “why connected” — one quiet keyword per lit edge (详略得当：论文标题为主，连线为辅)
 if(edgeLabels.length){
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.font = `italic 10px ${SERIF}`;
  for(const [ex,ey,l] of edgeLabels){
   let t=l.texts[0]; if(t.length>16)t=t.slice(0,15)+'…';
   const wpx = ctx.measureText(t).width+10;
   ctx.fillStyle = S.mode==='dark' ? 'rgba(8,6,4,0.6)' : 'rgba(248,242,229,0.75)';
   ctx.fillRect(ex-wpx/2, ey-8, wpx, 16);
   ctx.fillStyle = `rgba(${S.accentRGB},0.8)`;
   ctx.fillText(t, ex, ey);
  }
 }

 // stars
 app._stars.length = 0;
 const animByIdx = {};
 for(const a of app.anims){ animByIdx[a.i] = clamp((performance.now()-a.t0)/1800, 0, 1); }
 data.papers.forEach((p,i)=>{
  const [sx,sy] = w2s(app._wx[i],app._wy[i]);
  if(sx<-90||sx>vw+90||sy<-90||sy>vh+90){ app._stars.push(null); return; }
  let r = starR(p, cam.z), alpha = i===fi ? 0 : dim;
  if(neighbor && !neighbor.has(i)) alpha *= 0.35;   // hover: dim non-neighbours
  const q = animByIdx[i];
  if(q!==undefined){ r *= backOut(Math.min(1,q*1.3)); alpha *= Math.min(1,q*4); }
  if(app.hl && app.hl.papers.indexOf(i)>=0) alpha = Math.max(alpha, 0.95);
  app._stars.push({x:sx,y:sy,r,i});
  if(i===fi) return;
  R().drawStar(ctx, S, T, {x:sx,y:sy,r,hue:data.clusters[p.cluster].hue,
   heat:heatOf(p), seed:p.seed, alpha, time});
  if(app.hover && app.hover.kind==='star' && app.hover.i===i){  // pre-selection ring
   ctx.strokeStyle = `rgba(${S.inkRGB},0.55)`;
   ctx.setLineDash([2,3]); ctx.lineWidth=1;
   ctx.beginPath(); ctx.arc(sx,sy,r+6,0,TAU); ctx.stroke();
   ctx.setLineDash([]);
  }
 });
 // spatial grid for O(1) hit-testing (大库优化)
 app._grid.clear();
 for(const st of app._stars){
  if(!st) continue;
  const k=((st.x/72)|0)+','+((st.y/72)|0);
  let arr=app._grid.get(k);
  if(!arr){arr=[];app._grid.set(k,arr);}
  arr.push(st);
 }

 drawLabels(ctx, S, f, dim, time);
 const dts = Math.min(Math.max(time-(app._lastDrawT||time),0),0.1); app._lastDrawT=time;
 updateSky(ctx, S, time, dts, dim);
 if(app.hl) drawHl(ctx, S, f);
 if(app.focus) drawFocus(ctx, S, f, time);
 drawBirths(ctx, S);
 drawPings(ctx, S);
 drawDust(ctx, S, time, true);           // foreground floaters, over content
 if(S.mode==='dark'){
  const g = ctx.createRadialGradient(vw/2,vh/2,Math.min(vw,vh)*0.36,vw/2,vh/2,Math.max(vw,vh)*0.74);
  g.addColorStop(0,'rgba(0,0,0,0)'); g.addColorStop(1,'rgba(0,0,0,0.46)');
  ctx.fillStyle=g; ctx.fillRect(0,0,vw,vh);
 } else {
  R().drawPaperChrome(ctx, vw, vh, S, 1-0.7*f, time, app.view);   // marauder sheet dressing
 }
}

// parallax dust fields — the depth illusion: far layers pan/zoom less,
// the foreground layer over-shoots. Paper skin gets static foxing specks.
function drawDust(ctx, S, time, front){
 const c = app.cam;
 const dark = S.mode==='dark';
 for(const L of app.dust){
  if(L.blur !== front) continue;
  if(L.blur && !dark) continue;
  const zl = Math.max(0.08, 1 + (c.z-1)*L.f);
  for(const d of L.pts){
   const sx = (d.x - c.x*L.f)*zl + app.vw/2;
   const sy = (d.y - c.y*L.f)*zl + app.vh/2;
   if(sx<-40||sx>app.vw+40||sy<-40||sy>app.vh+40) continue;
   if(L.blur){
    const rr = d.r*(0.5+0.5*zl);
    const g = ctx.createRadialGradient(sx,sy,0,sx,sy,rr);
    g.addColorStop(0,`rgba(${S.inkRGB},${L.a})`);
    g.addColorStop(1,`rgba(${S.inkRGB},0)`);
    ctx.fillStyle=g; ctx.beginPath(); ctx.arc(sx,sy,rr,0,TAU); ctx.fill();
   } else {
    const a = L.a*(dark ? (0.65+0.35*Math.sin(time*1.3+d.tw)) : 0.4);
    ctx.fillStyle = `rgba(${S.inkRGB},${a})`;
    ctx.beginPath(); ctx.arc(sx,sy,d.r*(0.7+0.3*Math.min(zl,2)),0,TAU); ctx.fill();
   }
  }
 }
}

function drawLabels(ctx, S, f, dim, time){
 const {data, cam, vw} = app;
 // collision ledger + bg-halo strokes kill the “ghost text” overlaps
 const placed=[];
 const collide=(x,y,w,h)=>{for(const b of placed){if(Math.abs(x-b[0])*2<w+b[2]&&Math.abs(y-b[1])*2<h+b[3])return true;}return false;};
 const halo=(txt,x,y)=>{ctx.lineWidth=3;ctx.strokeStyle=`rgba(${S.bgRGB},0.8)`;ctx.strokeText(txt,x,y);};
 if(data.papers.length>=3){
  const a0 = (1-f)*clamp(2.5-cam.z, 0, 1);
  if(a0>0.02){
   ctx.textAlign='center'; ctx.textBaseline='alphabetic';
   for(const cl of data.clusters){
    if(cl.labelX===undefined) continue;
    const [sx,sy]=w2s(cl.labelX, cl.labelY);
    if(sx<-150||sx>vw+150) continue;
    const t1 = S.mode==='paper' ? '❦ '+cl.en.toUpperCase()+' ❦' : '⟨ '+cl.en.toUpperCase()+' ⟩';
    ctx.letterSpacing='1.2px';
    ctx.font = `14px ${FELL}`;
    halo(t1, sx, sy);
    ctx.fillStyle = S.hueStrong(cl.hue, 0.85*a0);
    ctx.fillText(t1, sx, sy);
    placed.push([sx, sy-6, ctx.measureText(t1).width, 16]);
    ctx.letterSpacing='0px';
    const t2 = cl.zh+' · '+data.papers.filter(p=>p.cluster===cl.idx).length+' 篇';
    ctx.font = `12px ${labelFont(cl.zh)}`;
    halo(t2, sx, sy+16);
    ctx.fillStyle = `rgba(${S.inkRGB},${0.55*a0})`;
    ctx.fillText(t2, sx, sy+16);
    placed.push([sx, sy+12, ctx.measureText(t2).width, 13]);
   }
  }
 }
 const a1 = clamp((cam.z-0.95)*2,0,1)*dim;
 ctx.textBaseline='middle';
 const hovI = (app.hover && app.hover.kind==='star' && !app.drag) ? app.hover.i : -1;
 const labelOne=(st,p,alpha,strong)=>{
  const side = p.seed%2 ? 1 : -1;
  ctx.textAlign = side>0?'left':'right';
  ctx.font = `${strong?'600 ':''}11.5px ${SERIF}`;
  let t=p.title; if(t.length>26) t=t.slice(0,25)+'…';
  const wpx = ctx.measureText(t).width;
  const lx = st.x + side*(st.r+8), ly = st.y;
  const bx = side>0 ? lx+wpx/2 : lx-wpx/2;
  if(!strong){ if(collide(bx,ly,wpx,14)) return; placed.push([bx,ly,wpx,14]); }
  halo(t, lx, ly);
  ctx.fillStyle = `rgba(${S.inkRGB},${alpha})`;
  ctx.fillText(t, lx, ly);
 };
 if(a1>0.02){
  app._stars.forEach(st=>{
   if(!st || !app.labelSet.has(st.i) || st.i===(app.focus&&app.focus.i) || st.i===hovI) return;
   labelOne(st, app.data.papers[st.i], 0.75*a1, false);
  });
 }
 if(hovI>=0){
  const st = app._stars[hovI];
  if(st && hovI!==(app.focus&&app.focus.i)) labelOne(st, app.data.papers[hovI], 0.97, true);
 }
}

function drawHl(ctx, S, f){
 const hl = app.hl;
 const focusSt = app.focus ? app._stars[app.focus.i] : null;
 ctx.lineWidth=1.1;
 const pts=[];
 for(const pi of hl.papers){
  if(app.focus && pi===app.focus.i) continue;
  let st = app._stars[pi];
  if(!st){ const p=app.data.papers[pi]; const [x,y]=w2s(app._wx?app._wx[pi]:p.x, app._wy?app._wy[pi]:p.y); st={x,y,r:starR(p,app.cam.z)}; }
  pts.push([st.x,st.y]);
  ctx.strokeStyle = `rgba(${S.accentRGB},0.9)`;
  ctx.setLineDash([3,4]);
  ctx.beginPath(); ctx.arc(st.x,st.y,st.r+9,0,TAU); ctx.stroke();
  ctx.setLineDash([]);
  if(focusSt){
   ctx.strokeStyle = `rgba(${S.accentRGB},0.3)`;
   ctx.setLineDash([2,5]);
   ctx.beginPath(); ctx.moveTo(focusSt.x,focusSt.y); ctx.lineTo(st.x,st.y); ctx.stroke();
   ctx.setLineDash([]);
  }
 }
 // 临时星座：join all occurrences of the entity and name the path
 if(pts.length>1 && !app.focus){
  let cx0=0,cy0=0; pts.forEach(q=>{cx0+=q[0];cy0+=q[1];}); cx0/=pts.length; cy0/=pts.length;
  const sorted=pts.slice().sort((A,B)=>Math.atan2(A[1]-cy0,A[0]-cx0)-Math.atan2(B[1]-cy0,B[0]-cx0));
  ctx.strokeStyle=`rgba(${S.accentRGB},0.45)`; ctx.setLineDash([4,5]); ctx.lineWidth=1;
  ctx.beginPath();
  sorted.forEach((q,j)=>{j?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});
  ctx.stroke(); ctx.setLineDash([]);
  let topY=1e9, topX=cx0;
  pts.forEach(q=>{if(q[1]<topY){topY=q[1];topX=q[0];}});
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.font=`italic 12px ${SERIF}`;
  ctx.fillStyle=`rgba(${S.accentRGB},0.95)`;
  ctx.fillText('✶ '+hl.text+' — '+hl.papers.length+' 篇', topX, topY-24);
 }
}

// ── focus scene: L1 section constellation / L2 section ring ─────────────────
function drawFocus(ctx, S, f, time){
 const F = app.focus, p = F.p;
 if(!p.sections){ return; }
 const [cx,cy] = w2s(app._wx[F.i], app._wy[F.i]);
 const ui = clamp(Math.min(app.vw,app.vh)/900, 0.72, 1.25);
 const sT = easeIO(F.secT);
 const g1 = f*(1-sT), g2 = f*sT;
 const hue = app.data.clusters[p.cluster].hue;
 const panelX = app.vw - 360;   // keep labels clear of the paper panel
 app._ents.length = 0; app._secs.length = 0;
 ctx.textBaseline='middle';

 // ── L1: reading-order constellation of sections ──
 if(g1>0.02){
  const R1=150*ui*(0.55+0.45*f), R2=228*ui*(0.6+0.4*f);
  const pts = F.layout.secs.map(o=>[cx+Math.cos(o.ang)*R1, cy+Math.sin(o.ang)*R1]);
  // spokes + reading chain
  ctx.strokeStyle=`rgba(${S.inkRGB},${0.13*g1})`; ctx.lineWidth=1;
  ctx.beginPath();
  pts.forEach(pt=>{ctx.moveTo(cx,cy);ctx.lineTo(pt[0],pt[1]);});
  ctx.stroke();
  ctx.strokeStyle=`rgba(${S.inkRGB},${0.4*g1})`;
  ctx.setLineDash([5,6]);
  ctx.beginPath();
  pts.forEach((pt,j)=>{j?ctx.lineTo(pt[0],pt[1]):ctx.moveTo(pt[0],pt[1]);});
  ctx.stroke(); ctx.setLineDash([]);
  // section nodes
  F.layout.secs.forEach((o,k)=>{
   const [sx,sy]=pts[k];
   const frac=o.s.chunks/Math.max(p.n_chunks,1);
   const nr=(10+24*frac)*ui;
   const hov=app.hover&&app.hover.kind==='sec'&&app.hover.k===k;
   ctx.save(); ctx.globalAlpha=g1;
   ctx.fillStyle=S.bg;
   ctx.beginPath();ctx.arc(sx,sy,nr,0,TAU);ctx.fill();
   ctx.restore();
   ctx.strokeStyle=S.hueStrong(hue,(hov?1:0.8)*g1); ctx.lineWidth=hov?1.6:1.1;
   ctx.beginPath();ctx.arc(sx,sy,nr,0,TAU);ctx.stroke();
   // entity ticks around the node
   const nt=Math.min(o.s.ents.length,14);
   ctx.strokeStyle=`rgba(${S.inkRGB},${0.5*g1})`; ctx.lineWidth=0.8;
   ctx.beginPath();
   for(let q=0;q<nt;q++){
    const an=q*TAU/nt-Math.PI/2;
    ctx.moveTo(sx+Math.cos(an)*(nr+2.5), sy+Math.sin(an)*(nr+2.5));
    ctx.lineTo(sx+Math.cos(an)*(nr+6), sy+Math.sin(an)*(nr+6));
   }
   ctx.stroke();
   ctx.textAlign='center';
   ctx.font=`600 ${Math.round(14*ui)}px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${0.95*g1})`;
   ctx.fillText(o.s.num, sx, sy+1);
   // label block below/above node, away from center
   const ly = sy + (sy>cy ? nr+20 : -(nr+24));
   ctx.font=`15px ${labelFont(o.s.zh)}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${(hov?1:0.85)*g1})`;
   ctx.fillText(o.s.zh, sx, ly);
   ctx.font=`11px ${FELL}`; ctx.letterSpacing='1px';
   ctx.fillStyle=`rgba(${S.inkRGB},${0.5*g1})`;
   ctx.fillText(o.s.en+' · '+o.s.chunks+' CH', sx, ly+14);
   ctx.letterSpacing='0px';
   if(hov){
    ctx.font=`italic 10.5px ${SERIF}`;
    ctx.fillStyle=`rgba(${S.accentRGB},${g1})`;
    ctx.fillText('点击下钻 ⟶ L2', sx, ly+(sy>cy?29:-(nr*2+38)+29));
   }
   app._secs.push({x:sx,y:sy,r:nr+12,k});
  });
  // key claim — the one-line takeaway, top center
  if(F.layout.claim){
   ctx.textAlign='center';
   ctx.font=`9px ${SERIF}`; ctx.letterSpacing='2px';
   ctx.fillStyle=`rgba(${S.accentRGB},${0.75*g1})`;
   ctx.fillText('✦ KEY CLAIM', cx, cy-R1-58*ui);
   ctx.letterSpacing='0px';
   ctx.font=`italic 13px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${0.9*g1})`;
   let t=F.layout.claim.text; if(t.length>46)t=t.slice(0,45)+'…';
   ctx.fillText('“'+t+'”', cx, cy-R1-40*ui);
  }
  // shared entities — outer ring, the doors to other papers
  F.layout.shared.forEach(o=>{
   const ex=cx+Math.cos(o.ang)*R2, ey=cy+Math.sin(o.ang)*R2;
   R().drawGlyph(ctx, o.e.type, ex, ey, 4.2, `rgba(${S.accentRGB},${0.9*g1})`, true);
   const right = Math.cos(o.ang)>=0 && ex < panelX-130;
   ctx.textAlign = right?'left':'right';
   ctx.font=`10.5px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${0.75*g1})`;
   let t=o.e.text; if(t.length>20)t=t.slice(0,19)+'…';
   ctx.fillText(t+' · '+o.n+'篇', ex+(right?13:-13), ey);
   app._ents.push({x:ex,y:ey,e:o.e,key:o.key,shared:true});
  });
  // cross-paper links of the focused star
  for(const l of app.focusLinks){
   const oi = l.a===F.i ? l.b : l.a;
   const op = app.data.papers[oi];
   const [ox,oy] = w2s(app._wx[oi], app._wy[oi]);
   ctx.strokeStyle = `rgba(${S.inkRGB},${0.35*g1})`; ctx.lineWidth=1;
   ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(ox,oy); ctx.stroke();
   ctx.fillStyle = `rgba(${S.accentRGB},${0.85*g1})`;
   ctx.beginPath(); ctx.arc(ox,oy,2.2,0,TAU); ctx.fill();
  }
 }

 // ── L2: one section, entities readable on a single ring ──
 if(F.sec!=null && g2>0.02 && F.items){
  const sec=p.sections[F.sec];
  const R3=192*ui*(0.7+0.3*sT);
  // hub title under the shrunken star
  ctx.textAlign='center';
  ctx.font=`${Math.round(22*ui)}px ${labelFont(sec.zh)}`;
  ctx.fillStyle=`rgba(${S.inkRGB},${0.95*g2})`;
  ctx.fillText('§'+sec.num+' '+sec.zh, cx, cy+30*ui);
  ctx.font=`9.5px ${FELL}`; ctx.letterSpacing='2px';
  ctx.fillStyle=`rgba(${S.inkRGB},${0.5*g2})`;
  ctx.fillText(sec.en+' · '+sec.chunks+' CHUNKS', cx, cy+46*ui);
  ctx.letterSpacing='0px';
  // ring
  ctx.strokeStyle=`rgba(${S.inkRGB},${0.22*g2})`; ctx.lineWidth=1;
  ctx.setLineDash([1.5,4]);
  ctx.beginPath();ctx.arc(cx,cy,R3,0,TAU);ctx.stroke();
  ctx.setLineDash([]);
  const m=F.items.length;
  if(m===0){
   ctx.font=`italic 12.5px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${0.75*g2})`;
   let t=sec.q?'? '+sec.q:'本节无抽取实体';
   if(t.length>40)t=t.slice(0,39)+'…';
   ctx.fillText(t, cx, cy-R3*0.55);
  }
  const pos={};
  F.items.forEach((it,j)=>{
   const ang=-Math.PI/2+j*TAU/Math.max(m,1);
   const ex=cx+Math.cos(ang)*R3, ey=cy+Math.sin(ang)*R3;
   pos[it.e.id]=[ex,ey];
   const key=GardenData.norm(it.e.text)+'|'+it.e.type;
   const rec=app.data.entIndex.get(key);
   const shared=rec&&rec.papers.length>1;
   const hov=app.hover&&app.hover.kind==='ent'&&app.hover.e.id===it.e.id;
   const col=shared?`rgba(${S.accentRGB},${0.95*g2})`:S.hueStrong(hue,0.9*g2);
   R().drawGlyph(ctx, it.e.type, ex, ey, hov?5.6:4.4, col, shared);
   const right = Math.cos(ang)>=-0.12 && ex < panelX-150;
   ctx.textAlign=right?'left':'right';
   ctx.font=`${hov||it.e.type==='parameter'?'600 ':''}12px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${(hov?1:0.85)*g2})`;
   let t=it.label; if(t.length>34)t=t.slice(0,33)+'…';
   ctx.fillText(t, ex+(right?14:-14), ey);
   if(shared){
    ctx.font=`9.5px ${SERIF}`;
    ctx.fillStyle=`rgba(${S.accentRGB},${0.8*g2})`;
    ctx.fillText(rec.papers.length+' 篇共享 · 点击高亮', ex+(right?14:-14), ey+13);
   }
   app._ents.push({x:ex,y:ey,e:it.e,key,shared:!!shared});
  });
  // intra-section relations with visible predicates
  for(const [s,pr,o] of p.relations){
   if(pr==='has_value'||pr==='in_unit')continue;
   const A=pos[s],B=pos[o]; if(!A||!B)continue;
   const mx=(A[0]+B[0])/2+(cx-(A[0]+B[0])/2)*0.45;
   const my=(A[1]+B[1])/2+(cy-(A[1]+B[1])/2)*0.45;
   ctx.strokeStyle=`rgba(${S.inkRGB},${0.3*g2})`; ctx.lineWidth=1;
   ctx.beginPath();ctx.moveTo(A[0],A[1]);ctx.quadraticCurveTo(mx,my,B[0],B[1]);ctx.stroke();
   ctx.textAlign='center';
   ctx.font=`italic 10px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${0.6*g2})`;
   ctx.fillText(pr, mx, my-4);
  }
  if(F.itemsHidden>0){
   ctx.textAlign='center';
   ctx.font=`italic 10.5px ${SERIF}`;
   ctx.fillStyle=`rgba(${S.inkRGB},${0.5*g2})`;
   ctx.fillText('+'+F.itemsHidden+' entities — 见右侧面板', cx, cy+R3+24);
  }
  ctx.textAlign='center';
  ctx.font=`10.5px ${SERIF}`;
  ctx.fillStyle=`rgba(${S.inkRGB},${0.45*g2})`;
  ctx.fillText('⎋ 或点击空白 · 返回论文俯瞰', cx, cy+R3+42);
 }

 // the focused star itself — shrinks as you drill deeper
 const st = app._stars[F.i];
 const r0 = st ? st.r : starR(p, app.cam.z);
 R().drawStar(ctx, S, T, {x:cx,y:cy,r:r0*(1+0.85*f*(1-0.72*sT)),hue,
  heat:heatOf(p), seed:p.seed, alpha:1, time, selected:f>0.5, rot:time*0.1*f});
}

// ── sky events: meteors, a rare comet, and — on parchment — wandering footprints
function updateSky(ctx, S, time, dts, dim){
 const sk = app.sky, dark = S.mode==='dark';
 // meteors (screen-space atmosphere)
 if(time > sk.nextMeteor){
  sk.nextMeteor = time + 5 + Math.random()*8;
  sk.meteors.push({x:Math.random()*app.vw, y:Math.random()*app.vh*0.45,
   ang:Math.PI*0.25+Math.random()*Math.PI*0.5,
   v:550+Math.random()*420, t0:time, life:0.7+Math.random()*0.5});
 }
 sk.meteors = sk.meteors.filter(m=>time-m.t0<m.life);
 for(const m of sk.meteors){
  const t=time-m.t0;
  const hx=m.x+Math.cos(m.ang)*m.v*t, hy=m.y+Math.sin(m.ang)*m.v*t;
  const L=70+m.v*0.06;
  const tx=hx-Math.cos(m.ang)*L, ty=hy-Math.sin(m.ang)*L;
  const al=Math.sin(Math.PI*Math.min(t/m.life,1))*dim;
  const g=ctx.createLinearGradient(tx,ty,hx,hy);
  if(dark){ g.addColorStop(0,'rgba(255,246,230,0)'); g.addColorStop(1,`rgba(255,246,230,${0.6*al})`); }
  else { g.addColorStop(0,`rgba(${S.inkRGB},0)`); g.addColorStop(1,`rgba(${S.inkRGB},${0.38*al})`); }
  ctx.strokeStyle=g; ctx.lineWidth=dark?1.4:1;
  ctx.beginPath(); ctx.moveTo(tx,ty); ctx.lineTo(hx,hy); ctx.stroke();
  if(dark){ ctx.fillStyle=`rgba(255,246,230,${0.85*al})`;
   ctx.beginPath(); ctx.arc(hx,hy,1.6,0,TAU); ctx.fill(); }
 }
 // comet — rare, slow, curved
 if(!sk.comet && time > sk.nextComet){
  sk.nextComet = time + 40 + Math.random()*35;
  const fromLeft = Math.random()<0.5;
  sk.comet = {t0:time, dur:11,
   p0:[fromLeft?-70:app.vw+70, app.vh*(0.12+Math.random()*0.3)],
   p2:[fromLeft?app.vw+90:-90, app.vh*(0.45+Math.random()*0.35)],
   cp:[app.vw*0.5+(Math.random()-0.5)*240, -70+Math.random()*180]};
 }
 if(sk.comet){
  const c=sk.comet, q=(time-c.t0)/c.dur;
  if(q>=1){ sk.comet=null; }
  else{
   const bez=t=>{const u=1-t;return [u*u*c.p0[0]+2*u*t*c.cp[0]+t*t*c.p2[0], u*u*c.p0[1]+2*u*t*c.cp[1]+t*t*c.p2[1]];};
   const [hx,hy]=bez(q);
   const [px,py]=bez(Math.max(q-0.02,0));
   const ang=Math.atan2(hy-py,hx-px)+Math.PI;   // tail trails behind
   const al=Math.pow(Math.sin(Math.PI*Math.min(Math.max(q,0),1)),0.5)*dim;
   if(dark){
    // three wisp strands that sway, ember particles, diffraction-cross head
    for(let s2=0;s2<3;s2++){
     const a2=ang+(s2-1)*0.11;
     const L2=92+s2*16;
     const sway=Math.sin(time*1.8+s2*2.1)*9;
     ctx.strokeStyle=`rgba(${S.accentRGB},${(0.30-0.08*Math.abs(s2-1))*al})`;
     ctx.lineWidth=1.2;
     ctx.beginPath(); ctx.moveTo(hx,hy);
     ctx.quadraticCurveTo(
      hx+Math.cos(a2)*L2*0.5+Math.cos(a2+Math.PI/2)*sway,
      hy+Math.sin(a2)*L2*0.5+Math.sin(a2+Math.PI/2)*sway,
      hx+Math.cos(a2)*L2, hy+Math.sin(a2)*L2);
     ctx.stroke();
    }
    for(let i2=0;i2<10;i2++){
     const tt=(i2/10+((time*0.6+i2*0.37)%0.1));
     const ja=ang+Math.sin(i2*3.7+time*1.3)*0.15;
     ctx.fillStyle=`rgba(255,246,230,${0.5*al*(1-tt)})`;
     ctx.beginPath(); ctx.arc(hx+Math.cos(ja)*(14+tt*95), hy+Math.sin(ja)*(14+tt*95), 0.9, 0, TAU); ctx.fill();
    }
    const g=ctx.createRadialGradient(hx,hy,0,hx,hy,7);
    g.addColorStop(0,`rgba(255,246,230,${0.95*al})`); g.addColorStop(1,'rgba(255,246,230,0)');
    ctx.fillStyle=g; ctx.beginPath(); ctx.arc(hx,hy,7,0,TAU); ctx.fill();
    ctx.strokeStyle=`rgba(255,246,230,${0.7*al})`; ctx.lineWidth=1;
    ctx.beginPath();
    ctx.moveTo(hx-6,hy); ctx.lineTo(hx+6,hy);
    ctx.moveTo(hx,hy-6); ctx.lineTo(hx,hy+6);
    ctx.stroke();
   } else {
    // engraved chart comet: ringed nucleus, fanned hatch rays, stipple between
    ctx.strokeStyle=`rgba(${S.inkRGB},${0.7*al})`; ctx.lineWidth=1;
    ctx.beginPath(); ctx.arc(hx,hy,2.6,0,TAU); ctx.stroke();
    ctx.fillStyle=`rgba(${S.inkRGB},${0.8*al})`;
    ctx.beginPath(); ctx.arc(hx,hy,1.1,0,TAU); ctx.fill();
    ctx.strokeStyle=`rgba(${S.accentRGB},${0.55*al})`;
    ctx.beginPath(); ctx.arc(hx,hy,4.6,0,TAU); ctx.stroke();
    ctx.strokeStyle=`rgba(${S.inkRGB},${0.5*al})`; ctx.lineWidth=0.9;
    ctx.beginPath();
    for(let i2=-2;i2<=2;i2++){
     const a2=ang+i2*0.085;
     ctx.moveTo(hx+Math.cos(a2)*7, hy+Math.sin(a2)*7);
     ctx.lineTo(hx+Math.cos(a2)*(64-Math.abs(i2)*9), hy+Math.sin(a2)*(64-Math.abs(i2)*9));
    }
    ctx.stroke();
    ctx.fillStyle=`rgba(${S.inkRGB},${0.35*al})`;
    for(let i2=0;i2<14;i2++){
     const tt=0.2+((i2*0.61)%0.75);
     const a2=ang+(((i2*0.37)%1)-0.5)*0.17;
     ctx.beginPath(); ctx.arc(hx+Math.cos(a2)*tt*60, hy+Math.sin(a2)*tt*60, 0.7, 0, TAU); ctx.fill();
    }
   }
  }
 }
 // marauder footprints — parchment only, in world space (pan/zoom with the map)
 if(!dark && app.data.clusters.length){
  const wk=sk.walker;
  const pickTarget=()=>{const c=app.data.clusters[Math.floor(Math.random()*app.data.clusters.length)];
   wk.tx=(c.cx||0)+(Math.random()-0.5)*260; wk.ty=(c.cy||0)+(Math.random()-0.5)*220;};
  if(!wk.init){ wk.init=true; const c=app.data.clusters[0]; wk.x=c.cx||0; wk.y=c.cy||0; pickTarget(); }
  const dx=wk.tx-wk.x, dy=wk.ty-wk.y, d=Math.hypot(dx,dy);
  if(d<12) pickTarget();
  else{
   const sp=30*dts;
   wk.x+=dx/d*sp; wk.y+=dy/d*sp; wk.trav+=sp;
   if(wk.trav>13){ wk.trav=0; wk.side*=-1;
    wk.steps.push({x:wk.x,y:wk.y,ang:Math.atan2(dy,dx),side:wk.side,t0:time});
    if(wk.steps.length>26) wk.steps.shift(); }
  }
  const sc=R().clamp(app.cam.z,0.5,2.2);
  for(const stp of wk.steps){
   const age=time-stp.t0; if(age>7) continue;
   const al=(1-age/7)*0.42*dim;
   const [sx,sy]=w2s(stp.x+Math.cos(stp.ang+Math.PI/2)*stp.side*3.2,
                     stp.y+Math.sin(stp.ang+Math.PI/2)*stp.side*3.2);
   ctx.save(); ctx.translate(sx,sy); ctx.rotate(stp.ang);
   ctx.fillStyle=`rgba(${S.inkRGB},${al})`;
   ctx.beginPath(); ctx.ellipse(0,0,3.4*sc,1.7*sc,0,0,TAU); ctx.fill();
   ctx.beginPath(); ctx.arc(4.6*sc,0,1.1*sc,0,TAU); ctx.fill();
   ctx.restore();
  }
 }
}

function drawBirths(ctx, S){
 const now = performance.now();
 app.anims = app.anims.filter(a => now-a.t0 < 1800);
 for(const a of app.anims){
  const q = (now-a.t0)/1800;
  const p = app.data.papers[a.i];
  const [sx,sy] = w2s(app._wx?app._wx[a.i]:p.x, app._wy?app._wy[a.i]:p.y);
  const al = Math.pow(1-q,1.5);
  ctx.strokeStyle = `rgba(${S.accentRGB},${al})`;
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(sx,sy,8+q*120,0,TAU); ctx.stroke();
  ctx.lineWidth = 1;
  ctx.strokeStyle = `rgba(${S.accentRGB},${al*0.6})`;
  ctx.beginPath(); ctx.arc(sx,sy,4+q*64,0,TAU); ctx.stroke();
 }
}

// click feedback — every tap answers with a small instrument ping
function drawPings(ctx, S){
 const now = performance.now();
 app.pings = app.pings.filter(p => now-p.t0 < 380);
 for(const p of app.pings){
  const q = (now-p.t0)/380;
  ctx.strokeStyle = `rgba(${S.accentRGB},${0.55*(1-q)})`;
  ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.arc(p.x,p.y,4+q*16,0,TAU); ctx.stroke();
 }
 ctx.lineWidth = 1;
}

// ── input ───────────────────────────────────────────────────────────────────
function hitStar(mx,my){
 let best=null, bd=1e9;
 const gx=(mx/72)|0, gy=(my/72)|0;
 for(let ix=gx-1;ix<=gx+1;ix++)for(let iy=gy-1;iy<=gy+1;iy++){
  const arr=app._grid.get(ix+','+iy);
  if(!arr) continue;
  for(const st of arr){
   const d = Math.hypot(mx-st.x,my-st.y);
   if(d < Math.max(14, st.r+6) && d<bd){ bd=d; best=st; }
  }
 }
 return best;
}
function hitEnt(mx,my){
 for(const en of app._ents){
  if(Math.hypot(mx-en.x,my-en.y) < 13) return en;
 }
 return null;
}
function hitSec(mx,my){
 for(const sc of app._secs){
  if(Math.hypot(mx-sc.x,my-sc.y) < sc.r) return sc;
 }
 return null;
}
function bindInput(){
 const cv = app.canvas;
 cv.addEventListener('wheel', e=>{
  e.preventDefault();
  const c = app.cam;
  const fac = Math.exp(-e.deltaY*0.0013);
  const nz = clamp(c.tz*fac, app.zFit*0.8, 6.5);
  const wx = (e.clientX-app.vw/2)/c.tz + c.tx;
  const wy = (e.clientY-app.vh/2)/c.tz + c.ty;
  c.tx = wx - (e.clientX-app.vw/2)/nz;
  c.ty = wy - (e.clientY-app.vh/2)/nz;
  c.tz = nz;
  if(app.view==='obs' && nz > app.zFit*1.22) toAtlas();
  else if(app.view==='atlas' && nz < app.zFit*1.05) toObs();
  else if(app.view==='focus' && nz < 1.42) exitFocus();
 }, {passive:false});

 cv.addEventListener('pointerdown', e=>{
  app.hover = null;   // kill hover ghosts while pressing/dragging
  app.drag = {x:e.clientX,y:e.clientY,cx:app.cam.tx,cy:app.cam.ty,moved:false};
  cv.setPointerCapture(e.pointerId);
 });
 cv.addEventListener('pointermove', e=>{
  app.mx=e.clientX; app.my=e.clientY;
  if(app.drag){
   const dx=e.clientX-app.drag.x, dy=e.clientY-app.drag.y;
   if(Math.hypot(dx,dy)>5) app.drag.moved=true;
   if(app.drag.moved){
    app.cam.tx = app.drag.cx - dx/app.cam.z;
    app.cam.ty = app.drag.cy - dy/app.cam.z;
    app.cam.x = app.cam.tx; app.cam.y = app.cam.ty;
   }
   cv.style.cursor='grabbing';
   return;
  }
  const F = app.focus;
  const ready = F && F.t>0.5;
  const sc = (ready && F.level===1) ? hitSec(e.clientX,e.clientY) : null;
  const en = (!sc && ready) ? hitEnt(e.clientX,e.clientY) : null;
  const st = (!sc && !en) ? hitStar(e.clientX,e.clientY) : null;
  app.hover = sc ? {kind:'sec',k:sc.k} : en ? {kind:'ent',e:en.e} : st ? {kind:'star',i:st.i} : null;
  cv.style.cursor = (sc||en||st) ? 'pointer' : 'grab';
 });
 cv.addEventListener('pointerup', e=>{
  const wasDrag = app.drag && app.drag.moved;
  app.drag = null;
  cv.style.cursor='grab';
  if(wasDrag) return;
  app.pings.push({x:e.clientX, y:e.clientY, t0:performance.now()});
  click(e.clientX, e.clientY);
 });

 // double-click = 快速推进一档 (obs/atlas only; in focus single-click semantics rule)
 cv.addEventListener('dblclick', e=>{
  e.preventDefault();
  if(app.view==='focus') return;
  if(hitStar(e.clientX,e.clientY)) return;   // star dblclick = just focus, no zoom jump
  const c = app.cam;
  const nz = clamp(c.tz*1.9, app.zFit*0.8, 6.5);
  const wx = (e.clientX-app.vw/2)/c.z + c.x;
  const wy = (e.clientY-app.vh/2)/c.z + c.y;
  c.tx = wx - (e.clientX-app.vw/2)/nz;
  c.ty = wy - (e.clientY-app.vh/2)/nz;
  c.tz = nz;
  if(app.view==='obs' && nz > app.zFit*1.22) toAtlas();
 });

 window.addEventListener('keydown', e=>{
  if(e.key==='Escape'){
   if(GardenHud.manualOpen()){ GardenHud.toggleManual(false); return; }
   if(GardenHud.seekOpen()){ GardenHud.toggleSeek(false); return; }
   if(app.hl){ clearHl(); return; }
   if(app.view==='focus'){
    if(app.focus && app.focus.level===2){ undrill(); return; }
    exitFocus(); return;
   }
   if(app.view==='atlas'){ toObs(); return; }
  }
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==='k'){ e.preventDefault(); GardenHud.toggleSeek(); }
  else if(e.key==='?' && document.activeElement.tagName!=='INPUT'){
   e.preventDefault(); GardenHud.toggleManual();
  }
  else if(e.key==='/' && !GardenHud.seekOpen() && document.activeElement.tagName!=='INPUT'){
   e.preventDefault(); GardenHud.toggleSeek(true);
  }
 });
}
function click(mx,my){
 if(app.focus && app.focus.t>0.5){
  if(app.focus.level===1){
   const sc = hitSec(mx,my);
   if(sc){ drillSection(sc.k); return; }
  }
  const en = hitEnt(mx,my);
  if(en){
   if(en.shared){ if(app.hl && app.hl.key===en.key) clearHl(); else setHl(en.key); }
   return;
  }
  const st = hitStar(mx,my);
  if(st && st.i!==app.focus.i){ focusPaper(app.data.papers[st.i]); return; }
  if(st) return;
  if(app.focus.level===2){ undrill(); return; }
  const [cx,cy]=w2s(app.focus.p.x,app.focus.p.y);
  if(Math.hypot(mx-cx,my-cy) > 246*1.3+50){ exitFocus(); }
  return;
 }
 const st = hitStar(mx,my);
 if(st){ focusPaper(app.data.papers[st.i]); return; }
 if(app.hl) clearHl();
}

return {init, applyTweaks, ingest, focusPaper, drillSection, undrill,
  locateEntity, toObs, exitFocus, clearHl,
  get app(){return app;}, get T(){return T;}, heatOf};
})();
