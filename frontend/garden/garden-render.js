// lazy-paper garden — canvas renderer
// All drawing is hand-rolled Canvas 2D: engraved star bodies, diffraction
// spikes, nebula brushes per skin. No chart library on purpose (§1.3).
window.GardenRender = (() => {
'use strict';

const TAU = Math.PI * 2;

// ── skins ───────────────────────────────────────────────────────────────────
const SKINS = {
 dark: {
  mode: 'dark', bg: '#0E0C09', bgRGB: '14,12,9',
  ink: '#EDE5D6', inkRGB: '237,229,214',
  accent: '#D97757', accentRGB: '217,119,87',
  starCore: '#FFF6E6',
  hue: (h, a) => `oklch(80% 0.12 ${h} / ${a})`,
  hueStrong: (h, a) => `oklch(86% 0.14 ${h} / ${a})`,
  nebMul: 1.35, gratA: 0.11,
 },
 paper: {
  mode: 'paper', bg: '#F2EBDC', bgRGB: '242,235,220',
  ink: '#2B2418', inkRGB: '43,36,24',
  accent: '#B5512D', accentRGB: '181,81,45',
  starCore: '#2B2418',
  hue: (h, a) => `oklch(44% 0.09 ${h} / ${a})`,
  hueStrong: (h, a) => `oklch(38% 0.10 ${h} / ${a})`,
  nebMul: 1.0, gratA: 0.10,
 },
 myc: {
  mode: 'dark', bg: '#0C110D', bgRGB: '12,17,13',
  ink: '#E1E8D8', inkRGB: '225,232,216',
  accent: '#D97757', accentRGB: '217,119,87',
  starCore: '#F4FAEA',
  hue: (h, a) => `oklch(82% 0.10 ${h} / ${a})`,
  hueStrong: (h, a) => `oklch(87% 0.12 ${h} / ${a})`,
  nebMul: 1.3, gratA: 0.10,
 },
};

// ── small math helpers ──────────────────────────────────────────────────────
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

function hullOf(pts){ // monotone chain, pts: [[x,y],...]
 const p = pts.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
 if (p.length < 3) return p;
 const cross=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
 const lo=[],hi=[];
 for(const q of p){while(lo.length>=2&&cross(lo[lo.length-2],lo[lo.length-1],q)<=0)lo.pop();lo.push(q);}
 for(let i=p.length-1;i>=0;i--){const q=p[i];while(hi.length>=2&&cross(hi[hi.length-2],hi[hi.length-1],q)<=0)hi.pop();hi.push(q);}
 lo.pop();hi.pop();return lo.concat(hi);
}
function expandHull(h, d){
 let cx=0,cy=0;h.forEach(p=>{cx+=p[0];cy+=p[1];});cx/=h.length;cy/=h.length;
 return h.map(p=>{const dx=p[0]-cx,dy=p[1]-cy,L=Math.hypot(dx,dy)||1;
  return [p[0]+dx/L*d, p[1]+dy/L*d];});
}
function chaikin(pts, it){
 let p = pts;
 for(let k=0;k<it;k++){
  const o=[];
  for(let i=0;i<p.length;i++){
   const a=p[i],b=p[(i+1)%p.length];
   o.push([a[0]*0.75+b[0]*0.25, a[1]*0.75+b[1]*0.25]);
   o.push([a[0]*0.25+b[0]*0.75, a[1]*0.25+b[1]*0.75]);
  }
  p=o;
 }
 return p;
}
function tracePath(ctx, pts){
 ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
 for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i][0],pts[i][1]);
 ctx.closePath();
}

// ── static world layer (graticule + nebula brush per skin) ──────────────────
const W = 820, LS = 0.8;
function buildLayer(data, T){
 const S = SKINS[T.skin];
 const size = Math.ceil(2*W*LS);
 const cv = document.createElement('canvas');
 cv.width = size; cv.height = size;
 const c = cv.getContext('2d');
 const w = x => (x+W)*LS;
 const neb = (T.nebula/100) * S.nebMul;

 // graticule — the instrument feel: polar grid + degree ring
 c.strokeStyle = `rgba(${S.inkRGB},${S.gratA})`;
 c.lineWidth = 1;
 for(let r=150;r<=750;r+=150){c.beginPath();c.arc(w(0),w(0),r*LS,0,TAU);c.stroke();}
 for(let i=0;i<12;i++){
  const a=i*TAU/12;c.beginPath();
  c.moveTo(w(Math.cos(a)*70),w(Math.sin(a)*70));
  c.lineTo(w(Math.cos(a)*760),w(Math.sin(a)*760));c.stroke();
 }
 c.strokeStyle = `rgba(${S.inkRGB},${S.gratA*1.6})`;
 for(let d=0;d<360;d+=3){
  const a=d*Math.PI/180, len=(d%15===0?13:6);
  c.beginPath();
  c.moveTo(w(Math.cos(a)*760),w(Math.sin(a)*760));
  c.lineTo(w(Math.cos(a)*(760+len)),w(Math.sin(a)*(760+len)));
  c.stroke();
 }
 c.fillStyle = `rgba(${S.inkRGB},0.3)`;
 c.font = '10px "Times New Roman", "Noto Serif SC", serif';
 c.textAlign='center';c.textBaseline='middle';
 for(let d=0;d<360;d+=30){
  const a=d*Math.PI/180;
  c.fillText(d+'°', w(Math.cos(a)*792), w(Math.sin(a)*792));
 }
 // zodiac as TINY CONSTELLATIONS just inside the instrument ring —
 // little linked stars instead of font glyphs (which render as emoji on some platforms)
 const CONS=[
  {p:[[0,55],[30,35],[65,25],[100,40]],e:[[0,1],[1,2],[2,3]]},                    // Ari
  {p:[[0,15],[35,45],[75,10],[55,70],[80,95]],e:[[0,1],[2,1],[1,3],[3,4]]},       // Tau
  {p:[[15,5],[10,90],[70,10],[75,95],[15,45],[72,50]],e:[[0,4],[4,1],[2,5],[5,3],[4,5]]}, // Gem
  {p:[[50,0],[45,45],[10,85],[85,80]],e:[[0,1],[1,2],[1,3]]},                     // Cnc
  {p:[[80,15],[55,5],[35,20],[40,45],[70,55],[5,85]],e:[[0,1],[1,2],[2,3],[3,4],[3,5]]}, // Leo
  {p:[[10,10],[35,30],[30,60],[60,75],[95,60],[55,100]],e:[[0,1],[1,2],[2,3],[3,4],[3,5]]}, // Vir
  {p:[[20,30],[80,25],[50,0],[15,85],[85,90]],e:[[2,0],[2,1],[0,1],[0,3],[1,4]]}, // Lib
  {p:[[5,10],[25,30],[40,55],[60,75],[85,80],[95,55]],e:[[0,1],[1,2],[2,3],[3,4],[4,5]]}, // Sco
  {p:[[10,70],[40,55],[70,60],[55,30],[90,25],[80,90]],e:[[0,1],[1,2],[1,3],[3,4],[2,5]]}, // Sgr
  {p:[[5,30],[50,15],[95,35],[70,80],[30,75]],e:[[0,1],[1,2],[2,3],[3,4],[4,0]]}, // Cap
  {p:[[0,40],[25,25],[50,45],[75,25],[100,45],[60,85]],e:[[0,1],[1,2],[2,3],[3,4],[2,5]]}, // Aqr
  {p:[[5,90],[30,60],[60,35],[90,10],[75,45],[45,80]],e:[[0,1],[1,2],[2,3],[2,4],[1,5]]}, // Psc
 ];
 const drawCons=(cx2,cy2,def)=>{
  const sc2=1.05*LS;   // ×3 — a quiet border band of constellations
  const pts=def.p.map(q=>[cx2+(q[0]-50)*sc2, cy2+(q[1]-50)*sc2]);
  c.strokeStyle=`rgba(${S.inkRGB},${S.mode==='dark'?0.14:0.18})`;
  c.lineWidth=0.9;
  c.beginPath();
  def.e.forEach(ed=>{c.moveTo(pts[ed[0]][0],pts[ed[0]][1]);c.lineTo(pts[ed[1]][0],pts[ed[1]][1]);});
  c.stroke();
  pts.forEach((q,j)=>{
   const rr=j===0?3.1:1.9;
   if(S.mode==='dark'){
    c.fillStyle='rgba(255,246,230,0.12)';
    c.beginPath();c.arc(q[0],q[1],rr*2.3,0,TAU);c.fill();
    c.fillStyle='rgba(255,246,230,0.5)';
   } else c.fillStyle=`rgba(${S.inkRGB},0.34)`;
   c.beginPath();c.arc(q[0],q[1],rr,0,TAU);c.fill();
   if(j===0 && S.mode==='dark'){   // main star gets a tiny cross, same language as the chart
    c.strokeStyle='rgba(255,246,230,0.28)';c.lineWidth=0.8;
    c.beginPath();
    c.moveTo(q[0]-rr*2.6,q[1]);c.lineTo(q[0]+rr*2.6,q[1]);
    c.moveTo(q[0],q[1]-rr*2.6);c.lineTo(q[0],q[1]+rr*2.6);
    c.stroke();
   }
  });
 };
 for(let i=0;i<12;i++){
  const a=(i*30+15)*Math.PI/180;
  drawCons(w(Math.cos(a)*655), w(Math.sin(a)*655), CONS[i]);
 }
 // pole emblem at the origin — the survey's anchor point
 {
  const ox=w(0), oy=w(0);
  c.strokeStyle=`rgba(${S.inkRGB},0.38)`; c.lineWidth=1;
  c.setLineDash([2,4]);
  c.beginPath();c.arc(ox,oy,40*LS,0,TAU);c.stroke();
  c.beginPath();c.arc(ox,oy,54*LS,0,TAU);c.stroke();
  c.setLineDash([]);
  c.strokeStyle=`rgba(${S.inkRGB},0.5)`;
  c.beginPath();
  for(let i=0;i<16;i++){
   const a=i*TAU/16, len=(i%2?14:27)*LS;
   c.moveTo(ox+Math.cos(a)*5, oy+Math.sin(a)*5);
   c.lineTo(ox+Math.cos(a)*len, oy+Math.sin(a)*len);
  }
  c.stroke();
  c.fillStyle = S.mode==='paper' ? `rgba(${S.accentRGB},0.8)` : 'rgba(255,246,230,0.9)';
  c.beginPath();c.arc(ox,oy,2.2,0,TAU);c.fill();
  c.fillStyle=`rgba(${S.inkRGB},0.42)`;
  c.font='11px "Ma Shan Zheng","Noto Serif SC",serif';
  c.fillText('巡天原点 · POLE', ox, oy+72*LS);
 }
 // milky way — a faint diagonal river fills the dark emptiness
 if(S.mode==='dark'){
  const mrnd=mulberry32(31337);
  const dirA=-0.55, ca=Math.cos(dirA), sa=Math.sin(dirA);
  c.globalCompositeOperation='lighter';
  for(let i=0;i<110;i++){
   const t=(mrnd()*2-1)*860;
   const off=(mrnd()+mrnd()+mrnd()-1.5)*150;
   const bx=w(t*ca-off*sa), by=w(t*sa+off*ca);
   const rr=(30+mrnd()*70)*LS;
   const g=c.createRadialGradient(bx,by,0,bx,by,rr);
   g.addColorStop(0,`rgba(${S.inkRGB},${0.014+mrnd()*0.02})`);
   g.addColorStop(1,'rgba(0,0,0,0)');
   c.fillStyle=g;c.beginPath();c.arc(bx,by,rr,0,TAU);c.fill();
  }
  c.globalCompositeOperation='source-over';
  c.fillStyle=`rgba(${S.inkRGB},1)`;
  for(let i=0;i<240;i++){
   const t=(mrnd()*2-1)*880;
   const off=(mrnd()+mrnd()+mrnd()-1.5)*170;
   c.globalAlpha=0.08+mrnd()*0.2;
   c.beginPath();c.arc(w(t*ca-off*sa),w(t*sa+off*ca),0.7,0,TAU);c.fill();
  }
  c.globalAlpha=1;
 }

 if (neb <= 0.01) return cv;
 const densL = Math.min(1, Math.sqrt(70/Math.max(data.papers.length,20)));
 // parchment aging — stains & coffee rings under the chart (paper skin only)
 if (T.skin === 'paper'){
  const rs = mulberry32(909);
  for(let i=0;i<11;i++){
   const bx=w((rs()*2-1)*700), by=w((rs()*2-1)*700), br=(50+rs()*120)*LS;
   const g=c.createRadialGradient(bx,by,0,bx,by,br);
   const al=0.03+rs()*0.045;
   g.addColorStop(0,`rgba(118,84,38,${al})`);
   g.addColorStop(0.7,`rgba(118,84,38,${al*0.5})`);
   g.addColorStop(1,'rgba(118,84,38,0)');
   c.fillStyle=g;c.beginPath();c.arc(bx,by,br,0,TAU);c.fill();
  }
  for(let i=0;i<5;i++){
   const bx=w((rs()*2-1)*650), by=w((rs()*2-1)*650), br=(22+rs()*40)*LS;
   c.strokeStyle=`rgba(112,76,32,${0.05+rs()*0.06})`;
   c.lineWidth=1.2+rs()*1.6;
   const a0=rs()*TAU, a1=a0+TAU*(0.55+rs()*0.4);
   c.beginPath();c.arc(bx,by,br,a0,a1);c.stroke();
  }
 }
 // nebulae per cluster
 for(const cl of data.clusters){
  const pts = data.papers.filter(p=>p.cluster===cl.idx).map(p=>[p.x,p.y]);
  if (pts.length < 2) continue;
  let cx=0,cy=0;pts.forEach(p=>{cx+=p[0];cy+=p[1];});cx/=pts.length;cy/=pts.length;
  const rnd = mulberry32(1000+cl.idx*77);

  if (T.skin === 'paper') {
   // engraved chart: tinted wash + wobbled dashed outline + stipple
   if (pts.length >= 3) {
    let h = chaikin(expandHull(hullOf(pts), 52), 3);
    h = h.map((p,i)=>{const n=Math.sin(i*1.7+cl.idx)*4;return [p[0]+n,p[1]+n*0.6];});
    const path = h.map(p=>[w(p[0]),w(p[1])]);
    tracePath(c, path);
    c.fillStyle = S.hue(cl.hue, 0.07*neb*1.4); c.fill();
    c.setLineDash([7,4]);
    c.strokeStyle = S.hue(cl.hue, 0.5); c.lineWidth=1.1; c.stroke();
    c.setLineDash([]);
   }
   c.fillStyle = S.hue(cl.hue, 0.16);
   for(let i=0;i<70*neb;i++){
    const a=rnd()*TAU, rr=Math.pow(rnd(),0.5);
    const px=cx+Math.cos(a)*rr*cl.sx*1.05, py=cy+Math.sin(a)*rr*cl.sy*1.05;
    c.beginPath();c.arc(w(px),w(py),0.9,0,TAU);c.fill();
   }
  } else if (T.skin === 'myc') {
   // mycelial growth network: recursive hyphae with node swellings,
   // anastomosis links between neighbouring stars, spore dust
   const heartG=c.createRadialGradient(w(cx),w(cy),0,w(cx),w(cy),80*LS);
   heartG.addColorStop(0,S.hue(cl.hue,0.20*neb));heartG.addColorStop(1,S.hue(cl.hue,0));
   c.fillStyle=heartG;c.beginPath();c.arc(w(cx),w(cy),80*LS,0,TAU);c.fill();
   const hypha=(x0,y0,x1,y1,wd,al,depth)=>{
    const segs=4+Math.floor(rnd()*3);
    let px=x0,py=y0;
    const dx=(x1-x0)/segs, dy=(y1-y0)/segs;
    const L=Math.hypot(x1-x0,y1-y0)||1;
    const nx=-(y1-y0)/L, ny=(x1-x0)/L;
    c.strokeStyle=S.hue(cl.hue,al);
    c.lineWidth=wd*LS;
    c.beginPath();c.moveTo(w(px),w(py));
    const mids=[];
    for(let s2=1;s2<=segs;s2++){
     const j=(rnd()-0.5)*L*0.16*(s2<segs?1:0.2);
     const qx=x0+dx*s2+nx*j, qy=y0+dy*s2+ny*j;
     c.quadraticCurveTo(w(px+dx*0.5+nx*j*0.5),w(py+dy*0.5+ny*j*0.5),w(qx),w(qy));
     mids.push([qx,qy]);px=qx;py=qy;
    }
    c.stroke();
    for(const [bx,by] of mids){
     if(rnd()<0.30){c.fillStyle=S.hue(cl.hue,Math.min(al*1.4,0.6));
      c.beginPath();c.arc(w(bx),w(by),1.5*LS*wd,0,TAU);c.fill();}
     if(depth>0&&rnd()<0.38){
      const ba=Math.atan2(y1-y0,x1-x0)+(rnd()<0.5?1:-1)*(0.5+rnd()*0.7);
      const bl=L*(0.18+rnd()*0.22);
      hypha(bx,by,bx+Math.cos(ba)*bl,by+Math.sin(ba)*bl,wd*0.6,al*0.7,depth-1);
     }
    }
   };
   for(const p of pts) hypha(cx,cy,p[0],p[1],1.3,(0.20+rnd()*0.12)*neb*1.5,2);
   for(let i=0;i<pts.length;i++)for(let j2=i+1;j2<pts.length;j2++){
    const d=Math.hypot(pts[i][0]-pts[j2][0],pts[i][1]-pts[j2][1]);
    if(d<95&&rnd()<0.5*densL) hypha(pts[i][0],pts[i][1],pts[j2][0],pts[j2][1],0.6,0.13*neb*1.5,0);
   }
   c.fillStyle=S.hue(cl.hue,0.30*neb);
   for(let i=0;i<45*neb;i++){
    const a=rnd()*TAU, rr2=Math.pow(rnd(),0.5);
    c.beginPath();c.arc(w(cx+Math.cos(a)*rr2*cl.sx*1.1),w(cy+Math.sin(a)*rr2*cl.sy*1.1),0.8,0,TAU);c.fill();
   }
  } else {
   // dark sky: additive gas blobs
   c.globalCompositeOperation='lighter';
   for(const p of pts){
    const rr=110*Math.max(densL,0.6)*LS;
    const g=c.createRadialGradient(w(p[0]),w(p[1]),0,w(p[0]),w(p[1]),rr);
    g.addColorStop(0,S.hue(cl.hue,0.05*neb*1.6*densL));g.addColorStop(1,S.hue(cl.hue,0));
    c.fillStyle=g;c.beginPath();c.arc(w(p[0]),w(p[1]),rr,0,TAU);c.fill();
   }
   const g=c.createRadialGradient(w(cx),w(cy),0,w(cx),w(cy),190*LS);
   g.addColorStop(0,S.hue(cl.hue,0.07*neb*1.6));g.addColorStop(1,S.hue(cl.hue,0));
   c.fillStyle=g;c.beginPath();c.arc(w(cx),w(cy),190*LS,0,TAU);c.fill();
   c.globalCompositeOperation='source-over';
   if (pts.length >= 3) {
    const h = chaikin(expandHull(hullOf(pts), 46), 3).map(p=>[w(p[0]),w(p[1])]);
    tracePath(c, h);
    c.setLineDash([2,5]);
    c.strokeStyle = S.hue(cl.hue, 0.22); c.lineWidth=1; c.stroke();
    c.setLineDash([]);
   }
  }
  cl.labelX = cx; cl.labelY = cy - cl.sy*1.18 - 38;
 }
 return cv;
}

// ── star body: engraved core + diffraction spikes ───────────────────────────
function spike(ctx, x, y, ang, len, w){
 ctx.save();ctx.translate(x,y);ctx.rotate(ang);
 ctx.beginPath();
 ctx.moveTo(0,-w);ctx.lineTo(len,0);ctx.lineTo(0,w);ctx.closePath();
 ctx.fill();
 ctx.restore();
}
function drawStar(ctx, S, T, o){
 // o: {x,y,r,hue,heat,seed,alpha,time,selected,birth}
 const {x,y,r,hue,heat,seed} = o;
 const a = o.alpha;
 if (a <= 0.01) return;
 const tw = 1 + 0.10*heat*Math.sin(o.time*6 + seed%100); // hot stars shimmer
 const form = T.spikeForm;

 if (S.mode === 'dark') {
  // every star carries a soft halo so the field reads as a sky, not voids;
  // hot (recent) stars additionally bloom in accent.
  ctx.globalCompositeOperation = 'lighter';
  const bg = r*4.0;
  const gb = ctx.createRadialGradient(x,y,0,x,y,bg);
  gb.addColorStop(0,`rgba(255,246,230,${0.30*a})`);
  gb.addColorStop(0.5,S.hue(hue,0.16*a));
  gb.addColorStop(1,`rgba(0,0,0,0)`);
  ctx.fillStyle=gb;ctx.beginPath();ctx.arc(x,y,bg,0,TAU);ctx.fill();
  if (heat > 0.02) {
   const gr = r*(3+6*heat);
   const g = ctx.createRadialGradient(x,y,0,x,y,gr);
   g.addColorStop(0,`rgba(${S.accentRGB},${0.5*heat*a*tw})`);
   g.addColorStop(1,`rgba(${S.accentRGB},0)`);
   ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,gr,0,TAU);ctx.fill();
  }
  ctx.globalCompositeOperation = 'source-over';
  const spikes = form==='six'?6 : form==='cross'?4 : 0;
  if (spikes){
   const len = r*(2.7+1.8*heat)*tw, wd = Math.max(0.7, r*0.16);
   ctx.fillStyle = S.hueStrong(hue, (0.5+0.3*heat)*a);
   const off = (seed%2)*(Math.PI/spikes)*0.5;
   for(let i=0;i<spikes;i++) spike(ctx,x,y,off+i*TAU/spikes - Math.PI/2, len, wd);
   if (r > 5.2){ // bright stars get a faint secondary cross
    ctx.fillStyle = S.hueStrong(hue, 0.22*a);
    for(let i=0;i<spikes;i++) spike(ctx,x,y,off+(i+0.5)*TAU/spikes - Math.PI/2, len*0.45, wd*0.7);
   }
  }
  ctx.fillStyle = `rgba(255,246,230,${(0.88+0.10*Math.sin(o.time*1.7+seed%40))*a*tw})`;
  ctx.beginPath();ctx.arc(x,y,r*0.62,0,TAU);ctx.fill();
  ctx.strokeStyle = S.hueStrong(hue, 1.0*a); ctx.lineWidth = 1.1;
  ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.stroke();
  if (form==='etch'){
   ctx.strokeStyle = S.hue(hue, 0.5*a);
   ctx.setLineDash([1.5,3]);
   ctx.beginPath();ctx.arc(x,y,r*1.7,0,TAU);ctx.stroke();
   ctx.setLineDash([]);
  }
  // engraved ticks
  const nT = 7 + seed%6;
  ctx.strokeStyle = S.hue(hue, 0.55*a); ctx.lineWidth = 0.8;
  ctx.beginPath();
  for(let i=0;i<nT;i++){
   const an = i*TAU/nT + (seed%17)*0.1 + (o.rot||0);
   const r1 = r*1.28, r2 = r1 + Math.max(2, r*0.45);
   ctx.moveTo(x+Math.cos(an)*r1, y+Math.sin(an)*r1);
   ctx.lineTo(x+Math.cos(an)*r2, y+Math.sin(an)*r2);
  }
  ctx.stroke();
 } else {
  // paper skin — pure engraving: ink body, hatched spikes, dashed heat rings
  const hueA = (al)=>S.hueStrong(hue, al*a);
  const spikes = form==='six'?6 : form==='cross'?4 : 0;
  if (spikes){
   ctx.strokeStyle = hueA(0.6); ctx.lineWidth = 0.9;
   const len = r*(2.9+1.4*heat);
   const off = (seed%2)*(Math.PI/spikes)*0.5;
   ctx.beginPath();
   for(let i=0;i<spikes;i++){
    const an = off+i*TAU/spikes - Math.PI/2;
    ctx.moveTo(x+Math.cos(an)*r*1.25, y+Math.sin(an)*r*1.25);
    ctx.lineTo(x+Math.cos(an)*len, y+Math.sin(an)*len);
   }
   ctx.stroke();
  }
  ctx.fillStyle = `rgba(${S.inkRGB},${0.92*a})`;
  ctx.beginPath();ctx.arc(x,y,r*0.5,0,TAU);ctx.fill();
  ctx.strokeStyle = hueA(0.85); ctx.lineWidth = 1;
  ctx.beginPath();ctx.arc(x,y,r*0.95,0,TAU);ctx.stroke();
  const nT = 7 + seed%6;
  ctx.strokeStyle = `rgba(${S.inkRGB},${0.5*a})`; ctx.lineWidth = 0.7;
  ctx.beginPath();
  for(let i=0;i<nT;i++){
   const an = i*TAU/nT + (seed%17)*0.1 + (o.rot||0);
   ctx.moveTo(x+Math.cos(an)*r*1.2, y+Math.sin(an)*r*1.2);
   ctx.lineTo(x+Math.cos(an)*(r*1.2+Math.max(2,r*0.4)), y+Math.sin(an)*(r*1.2+Math.max(2,r*0.4)));
  }
  ctx.stroke();
  if (form==='etch'){
   ctx.strokeStyle = hueA(0.4); ctx.setLineDash([1.5,3]);
   ctx.beginPath();ctx.arc(x,y,r*1.7,0,TAU);ctx.stroke();ctx.setLineDash([]);
  }
  // heat = concentric dashed accent rings (engraver's halo)
  const nH = Math.ceil(heat*3 - 0.12);
  if (nH > 0){
   ctx.strokeStyle = `rgba(${S.accentRGB},${0.65*heat*a})`;
   ctx.lineWidth = 0.8; ctx.setLineDash([2,3.5]);
   for(let i=1;i<=nH;i++){ctx.beginPath();ctx.arc(x,y,r*(1.4+i*0.75),0,TAU);ctx.stroke();}
   ctx.setLineDash([]);
  }
 }
 if (o.selected){
  ctx.strokeStyle = `rgba(${S.accentRGB},${0.9*a})`;
  ctx.lineWidth = 1.1; ctx.setLineDash([3,4]);
  ctx.beginPath();ctx.arc(x,y,r+7,0,TAU);ctx.stroke();
  ctx.setLineDash([]);
 }
}

// ── entity glyph vocabulary (11-type closed set, §6.2) ──────────────────────
function drawGlyph(ctx, type, x, y, s, col, accent){
 ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1.1;
 switch(type){
  case 'method': ctx.beginPath();ctx.arc(x,y,s,0,TAU);ctx.stroke();break;
  case 'material': ctx.beginPath();ctx.arc(x,y,s*0.9,0,TAU);ctx.fill();break;
  case 'dopant': ctx.beginPath();ctx.arc(x,y,s*0.45,0,TAU);ctx.fill();
   ctx.beginPath();ctx.arc(x,y,s,0,TAU);ctx.stroke();break;
  case 'parameter': ctx.beginPath();ctx.moveTo(x,y-s);ctx.lineTo(x+s,y);ctx.lineTo(x,y+s);ctx.lineTo(x-s,y);ctx.closePath();ctx.stroke();break;
  case 'value': ctx.beginPath();ctx.moveTo(x,y-s);ctx.lineTo(x,y+s);ctx.stroke();break;
  case 'unit': ctx.fillRect(x-s*0.55,y-s*0.55,s*1.1,s*1.1);break;
  case 'figure': ctx.strokeRect(x-s,y-s,s*2,s*2);break;
  case 'table': ctx.strokeRect(x-s,y-s,s*2,s*2);
   ctx.beginPath();ctx.moveTo(x-s,y);ctx.lineTo(x+s,y);ctx.moveTo(x,y-s);ctx.lineTo(x,y+s);ctx.stroke();break;
  case 'claim': ctx.beginPath();
   for(let i=0;i<3;i++){const a=i*Math.PI/3;
    ctx.moveTo(x-Math.cos(a)*s,y-Math.sin(a)*s);ctx.lineTo(x+Math.cos(a)*s,y+Math.sin(a)*s);}
   ctx.stroke();break;
  case 'comparator': ctx.beginPath();ctx.moveTo(x,y-s);ctx.lineTo(x+s,y+s*0.8);ctx.lineTo(x-s,y+s*0.8);ctx.closePath();ctx.stroke();break;
  case 'author': ctx.beginPath();ctx.moveTo(x-s,y);ctx.lineTo(x+s,y);ctx.moveTo(x,y-s);ctx.lineTo(x,y+s);
   ctx.moveTo(x-s*0.6,y-s*0.6);ctx.lineTo(x+s*0.6,y+s*0.6);ctx.moveTo(x+s*0.6,y-s*0.6);ctx.lineTo(x-s*0.6,y+s*0.6);ctx.stroke();break;
  default: ctx.beginPath();ctx.arc(x,y,s*0.7,0,TAU);ctx.stroke();
 }
 if (accent){
  ctx.setLineDash([1.5,2.5]);
  ctx.beginPath();ctx.arc(x,y,s+3.5,0,TAU);ctx.stroke();
  ctx.setLineDash([]);
 }
}

// ── orbit layout (L1): three tracks by type, deterministic angles ───────────
const TRACK = {method:0,material:0,dopant:0,parameter:1,value:1,unit:1};
const TRACK_NAMES = ['METHOD · MATERIAL','PARAMETER · VALUE','FIGURE · TABLE · CLAIM · AUTHOR'];
const TYPE_ORDER = ['method','material','dopant','parameter','value','unit','figure','table','claim','comparator','author'];
function layoutOrbits(paper){
 const byTrack = [[],[],[]];
 const ents = paper.entities.slice(0, 36);
 ents.forEach(e => byTrack[TRACK[e.type] !== undefined ? TRACK[e.type] : 2].push(e));
 const nodes = [];
 byTrack.forEach((list, tr) => {
  list.sort((a,b)=>TYPE_ORDER.indexOf(a.type)-TYPE_ORDER.indexOf(b.type) || (a.text<b.text?-1:1));
  const m = list.length;
  list.forEach((e, i) => {
   const ang = -Math.PI/2 + (tr*0.42) + i*TAU/Math.max(m,1) + ((paper.seed+i*31)%9-4)*0.012;
   nodes.push({e, track:tr, ang});
  });
 });
 return {nodes, hidden: paper.entities.length - ents.length};
}

// ── parallax dust: three depth layers for 纵深感 ──────────────────────────
function buildDust(){
 const rnd=mulberry32(424242);
 const layers=[
  {f:0.30,n:240,rr:[0.4,1.0],a:0.32,blur:false},   // far field — barely moves
  {f:0.62,n:120, rr:[0.5,1.5],a:0.5, blur:false},   // mid field
  {f:1.55,n:11, rr:[12,34], a:0.055,blur:true},    // foreground floaters — over-shoot
 ];
 layers.forEach(L=>{L.pts=[];
  for(let i=0;i<L.n;i++)L.pts.push({x:(rnd()*2-1)*1500,y:(rnd()*2-1)*1500,
   r:L.rr[0]+rnd()*(L.rr[1]-L.rr[0]),tw:rnd()*6.28});});
 return layers;
}

// ── marauder sheet dressing (paper skin): vignette, frame, flourishes, compass
function drawPaperChrome(ctx, vw, vh, S, a, time, view){
 // aged sepia vignette
 const g = ctx.createRadialGradient(vw/2,vh/2,Math.min(vw,vh)*0.32,vw/2,vh/2,Math.max(vw,vh)*0.75);
 g.addColorStop(0,'rgba(101,72,35,0)');
 g.addColorStop(0.8,'rgba(101,72,35,0.07)');
 g.addColorStop(1,'rgba(84,58,26,0.2)');
 ctx.fillStyle=g; ctx.fillRect(0,0,vw,vh);
 // double-line sheet frame
 ctx.strokeStyle=`rgba(${S.inkRGB},${0.5*a})`; ctx.lineWidth=1.2;
 ctx.strokeRect(11.5,11.5,vw-23,vh-23);
 ctx.strokeStyle=`rgba(${S.inkRGB},${0.3*a})`; ctx.lineWidth=0.7;
 ctx.strokeRect(17.5,17.5,vw-35,vh-35);
 // corner flourishes — ink curls
 ctx.strokeStyle=`rgba(${S.inkRGB},${0.55*a})`; ctx.lineWidth=1;
 const corners=[[11.5,11.5,1,1],[vw-11.5,11.5,-1,1],[vw-11.5,vh-11.5,-1,-1],[11.5,vh-11.5,1,-1]];
 for(const [x,y,sx,sy] of corners){
  ctx.beginPath();
  ctx.moveTo(x+sx*26, y);
  ctx.quadraticCurveTo(x+sx*8, y, x+sx*8, y+sy*8);
  ctx.quadraticCurveTo(x+sx*8, y+sy*26, x, y+sy*26);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x+sx*15, y+sy*15, 2.6, 0, TAU);
  ctx.stroke();
  ctx.fillStyle=`rgba(${S.accentRGB},${0.7*a})`;
  ctx.beginPath();ctx.arc(x+sx*15, y+sy*15, 0.9, 0, TAU);ctx.fill();
 }
 // compass rose — bottom right, breathing ever so slightly
 const cxp=vw-86, cyp=vh-88, r=42*(1+0.008*Math.sin(time*0.6));
 ctx.save(); ctx.globalAlpha=0.62*a; ctx.translate(cxp,cyp);
 ctx.strokeStyle=`rgba(${S.inkRGB},0.8)`; ctx.lineWidth=1;
 ctx.beginPath();ctx.arc(0,0,r,0,TAU);ctx.stroke();
 ctx.beginPath();ctx.arc(0,0,r*0.74,0,TAU);ctx.stroke();
 ctx.beginPath();
 for(let i=0;i<32;i++){const an=i*TAU/32;
  ctx.moveTo(Math.cos(an)*r*0.92,Math.sin(an)*r*0.92);
  ctx.lineTo(Math.cos(an)*r,Math.sin(an)*r);}
 ctx.stroke();
 const pt=(an,len,wd,fill)=>{
  ctx.beginPath();
  ctx.moveTo(Math.cos(an)*len,Math.sin(an)*len);
  ctx.lineTo(Math.cos(an+Math.PI/2)*wd,Math.sin(an+Math.PI/2)*wd);
  ctx.lineTo(Math.cos(an+Math.PI)*wd*2,Math.sin(an+Math.PI)*wd*2);
  ctx.lineTo(Math.cos(an-Math.PI/2)*wd,Math.sin(an-Math.PI/2)*wd);
  ctx.closePath();
  if(fill){ctx.fill();}else{ctx.stroke();}
 };
 ctx.fillStyle=`rgba(${S.accentRGB},0.85)`;
 pt(-Math.PI/2, r*0.7, 3.5, true);            // north — accent
 ctx.fillStyle=`rgba(${S.inkRGB},0.75)`;
 pt(0, r*0.7, 3.5, true); pt(Math.PI/2, r*0.7, 3.5, true); pt(Math.PI, r*0.7, 3.5, true);
 ctx.strokeStyle=`rgba(${S.inkRGB},0.6)`;
 for(let i=0;i<4;i++) pt(-Math.PI/4+i*Math.PI/2, r*0.42, 2.2, false);
 ctx.fillStyle=`rgba(${S.inkRGB},0.9)`;
 ctx.font='11px "Ma Shan Zheng","Noto Serif SC",serif';
 ctx.textAlign='center'; ctx.textBaseline='middle';
 ctx.fillText('北', 0, -r-9);
 ctx.restore();
 // cartouche — the old-map title plate with a scale bar (atlas/focus views)
 if(view && view!=='obs'){
  const x0=26, y0=46;
  ctx.strokeStyle=`rgba(${S.inkRGB},${0.55*a})`; ctx.lineWidth=1;
  ctx.strokeRect(x0+0.5, y0+0.5, 196, 80);
  ctx.strokeStyle=`rgba(${S.inkRGB},${0.28*a})`; ctx.lineWidth=0.6;
  ctx.strokeRect(x0+4.5, y0+4.5, 188, 72);
  ctx.textAlign='center'; ctx.textBaseline='alphabetic';
  ctx.fillStyle=`rgba(${S.inkRGB},${0.85*a})`;
  ctx.font='17px "Ma Shan Zheng","Noto Serif SC",serif';
  ctx.fillText('学 术 巡 天 图', x0+98, y0+27);
  ctx.letterSpacing='2px';
  ctx.font='7.5px "IM Fell English","Times New Roman",serif';
  ctx.fillStyle=`rgba(${S.inkRGB},${0.5*a})`;
  ctx.fillText('CHARTA CAELESTIS BIBLIOTHECAE', x0+98, y0+40);
  ctx.letterSpacing='0px';
  const bx=x0+38, by=y0+52, seg=24;
  ctx.strokeStyle=`rgba(${S.inkRGB},${0.7*a})`; ctx.lineWidth=1;
  ctx.strokeRect(bx+0.5, by+0.5, seg*5, 6);
  ctx.fillStyle=`rgba(${S.inkRGB},${0.7*a})`;
  for(let i=0;i<5;i+=2) ctx.fillRect(bx+i*seg, by, seg, 7);
  ctx.font='8px "Times New Roman","Noto Serif SC",serif';
  ctx.fillStyle=`rgba(${S.inkRGB},${0.55*a})`;
  ctx.fillText('0', bx, by+17);
  ctx.fillText('500 chunks', bx+seg*5-16, by+17);
 }
}

return {SKINS, buildLayer, drawStar, drawGlyph, layoutOrbits, TRACK_NAMES, buildDust, drawPaperChrome, clamp};
})();
