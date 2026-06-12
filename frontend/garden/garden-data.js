// lazy-paper garden — mock data layer
// Deterministic, seeded. Mirrors the real data contract (manifest + entities/relations)
// from the framework doc: every visual is driven by fields that exist in v1.14.
window.GardenData = (() => {
'use strict';

// ── seeded RNG ──────────────────────────────────────────────────────────────
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
function strHash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0;}
const norm=t=>String(t).toLowerCase().replace(/\s+/g,' ').trim();

// cluster hue angles (oklch). Accent #D97757 ≈ hue 40 — kept clear of it.
const HUES=[80,150,210,268,335,25];

// ── domain pools ────────────────────────────────────────────────────────────
const CLUSTER_DEFS=[
{key:'neq',en:'nonequilibrium · transport',zh:'非平衡输运',w:0.24,
 titles:['Entropy production bounds in driven lattice gases','驱动布朗粒子的涨落定理实验检验','Thermodynamic uncertainty relations far from equilibrium','Heat transport in boundary-driven spin chains','非平衡定态的大偏差函数计算','Stochastic resetting and first-passage statistics','Mpemba effect in colloidal quenches','Anomalous diffusion in crowded media'],
 keywords:['entropy production','fluctuation theorem','stochastic thermodynamics','first-passage','large deviations','resetting','anomalous diffusion','driven lattice'],
 materials:['colloidal silica bead','DNA hairpin','granular gas'],
 methods:['Langevin simulation','Gillespie algorithm','optical tweezers','large deviation theory'],
 params:['entropy production rate','Péclet number','first-passage time','effective temperature'],
 comparators:['SSEP','run-and-tumble model','equilibrium baseline'],
 claims:['TUR saturates near criticality','resetting accelerates search','heat statistics are non-Gaussian'],
 figs:['work distribution under driving','first-passage time histogram','entropy production vs drive','trajectory ensemble portrait'],
 questions:['TUR 的界在何种驱动下饱和?','重置策略的最优分布是否普适?','实验上如何区分主动与热涨落?','大偏差函数的数值收敛性如何保证?']},
{key:'sc',en:'superconductivity · nickelates',zh:'超导材料',w:0.20,
 titles:['Superconductivity in infinite-layer nickelates','镍酸盐薄膜中的超导电性与应变调控','Pseudogap and strange-metal transport in cuprates','Pressure-tuned Tc in La3Ni2O7 bilayers','STM spectroscopy of vortex cores in FeSe','铜氧化物中电荷密度波与超导的竞争','Nematic fluctuations and pairing symmetry','Isotope effects revisited in hydride superconductors'],
 keywords:['nickelates','cuprates','strange metal','pseudogap','strain tuning','vortex matter','pairing symmetry','high pressure'],
 materials:['La3Ni2O7','NdNiO2 film','YBCO crystal','FeSe monolayer'],
 dopants:['Sr doping','O vacancies'],
 methods:['STM spectroscopy','ARPES','pulsed-laser deposition','transport measurement'],
 params:['critical temperature Tc','upper critical field','residual resistivity','strain ε'],
 comparators:['cuprate phase diagram','BCS prediction'],
 claims:['Tc enhanced under compressive strain','pairing is d-wave','strange-metal scattering is Planckian'],
 figs:['R–T curves under strain','vortex-core dI/dV map','phase diagram vs doping','Tc vs pressure'],
 questions:['应变与掺杂的 Tc 调控是否同源?','赝能隙与超导序参量的关系?','镍酸盐与铜氧化物的配对机制是否一致?','高压相的结构稳定性如何?']},
{key:'llm',en:'LLM · reasoning',zh:'语言模型',w:0.20,
 titles:['Scaling laws for in-context retrieval','思维链推理中的自洽性度量','Emergent planning in autoregressive transformers','Sparse attention for million-token contexts','RLHF reward hacking: a taxonomy','大模型知识编辑的局部性评估','Grokking and the geometry of generalization','Tool-use agents under distribution shift'],
 keywords:['scaling laws','in-context learning','chain-of-thought','RLHF','knowledge editing','long context','agents','grokking'],
 materials:['Pile subset','synthetic CoT corpus','tool-use benchmark'],
 methods:['sparse attention','reward modeling','activation patching','curriculum distillation'],
 params:['context length','reward gap','edit locality score','effective rank'],
 comparators:['dense baseline','frozen reference model'],
 claims:['CoT length predicts accuracy','editing damages neighboring facts','retrieval emerges at scale'],
 figs:['accuracy vs context length','reward hacking onset','attention entropy by depth','loss landscape slice'],
 questions:['上下文检索的标度律是否随架构改变?','奖励黑客的早期信号是什么?','知识编辑的副作用如何量化?','长上下文的有效利用率多高?']},
{key:'act',en:'active matter · collectives',zh:'活性物质',w:0.14,
 titles:['Flocking transitions in motile colloids','活性湍流中的拓扑缺陷动力学','Motility-induced phase separation revisited','Collective foraging in robotic swarms','细菌悬浮液的流变学测量','Odd viscosity in chiral active fluids','Boundary accumulation of active rods'],
 keywords:['flocking','MIPS','topological defects','swarms','rheology','chiral fluids','bacterial suspension'],
 materials:['motile colloids','E. coli suspension','robotic swarm units'],
 methods:['particle tracking','Vicsek-type simulation','microrheology'],
 params:['polar order parameter','swim speed','defect density'],
 comparators:['passive Brownian control','dry flocking model'],
 claims:['MIPS requires persistence','defects order the flow','odd viscosity is measurable'],
 figs:['defect trajectories','phase separation snapshots','velocity correlation maps','order parameter vs density'],
 questions:['MIPS 的临界维度是多少?','奇异黏度在何种手性系统可测?','边界积累是否依赖水动力相互作用?']},
{key:'tn',en:'tensor networks · numerics',zh:'张量网络',w:0.12,
 titles:['DMRG study of the kagome antiferromagnet','二维系统的等距张量网络算法','Sign-problem-free Monte Carlo for moiré bands','Neural quantum states beyond variational limits','矩阵乘积态的纠缠熵标度','Krylov methods for open-system dynamics','Tensor cross interpolation for path integrals'],
 keywords:['DMRG','isometric TN','sign problem','neural quantum states','entanglement scaling','Krylov','path integrals'],
 materials:['kagome antiferromagnet','moiré flat band','open spin chain'],
 methods:['DMRG','variational Monte Carlo','tensor cross interpolation','Krylov propagation'],
 params:['bond dimension','entanglement entropy','truncation error'],
 comparators:['exact diagonalization','quantum Monte Carlo'],
 claims:['area law holds in 2D ground states','sign problem absent for moiré bands','modest χ suffices'],
 figs:['entanglement entropy scaling','energy vs bond dimension','spectral function map','convergence diagnostics'],
 questions:['等距张量网络的表达力上界?','神经量子态的优化景观是否光滑?','交叉插值的误差如何控制?']},
{key:'neuro',en:'neuromorphic · memristors',zh:'神经形态',w:0.10,
 titles:['Memristive crossbars for on-chip learning','忆阻器阵列中的随机权重更新','Spiking networks with dendritic delays','Phase-change synapses: drift and compensation','类脑芯片上的局部学习规则','Reservoir computing with nanowire networks'],
 keywords:['memristor crossbar','spiking networks','phase-change synapse','reservoir computing','local learning','drift'],
 materials:['HfO2 memristor array','Ag nanowire network','PCM synapse cell'],
 methods:['in-situ training','spike-timing protocol','conductance mapping'],
 params:['conductance drift rate','spike latency','energy per update'],
 comparators:['software backprop','ideal device model'],
 claims:['drift is compensable in-situ','local rules suffice at MNIST scale','nanowire memory is fading'],
 figs:['conductance drift traces','crossbar weight map','spike raster','energy per inference'],
 questions:['漂移补偿的能耗代价?','局部规则能否逼近反传?','纳米线网络的记忆容量标度?']}
];

const AUTHORS=['A. Mori','J. Tan','R. Vásquez','M. Oduya','S. Klein','H. Park','E. Rossi','T. Nakamura','D. Costa','P. Iyer','N. Volkov','C. Ladd'];
const UNITS=['K','meV','nm','GPa','k_B T','ms','μm/s'];
// plausible units per parameter — '' means dimensionless (no unit entity)
const PARAM_UNITS={'entropy production rate':'k_B/s','Péclet number':'','first-passage time':'ms',
 'effective temperature':'K','critical temperature Tc':'K','upper critical field':'T',
 'residual resistivity':'μΩ·cm','strain ε':'%','context length':'k tokens','reward gap':'',
 'edit locality score':'','effective rank':'','polar order parameter':'','swim speed':'μm/s',
 'defect density':'mm⁻²','bond dimension':'','entanglement entropy':'bits','truncation error':'',
 'conductance drift rate':'%/h','spike latency':'ms','energy per update':'pJ'};
const ROMAN=['II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];

// entities that genuinely live in 2+ fields → cross-nebula constellation lines
const SHARED=[
 {t:'Monte Carlo',type:'method',c:['neq','tn','act','sc']},
 {t:'Langevin dynamics',type:'method',c:['neq','act']},
 {t:'renormalization group',type:'method',c:['neq','tn','sc']},
 {t:'graphene',type:'material',c:['sc','tn','neuro']},
 {t:'Berry curvature',type:'parameter',c:['sc','tn']},
 {t:'attention',type:'method',c:['llm','neuro']},
 {t:'gradient descent',type:'method',c:['llm','neuro','tn']},
 {t:'Ising model',type:'comparator',c:['neq','tn','llm']},
 {t:'fluctuation–dissipation',type:'claim',c:['neq','act']},
 {t:'phase diagram',type:'comparator',c:['sc','neq','act','tn']},
 {t:'STM',type:'method',c:['sc','neuro']},
 {t:'entropy production',type:'parameter',c:['neq','act']},
 {t:'transformer',type:'method',c:['llm','neuro']},
 {t:'effective temperature',type:'parameter',c:['neq','act','sc']}
];

// ── paper factory ───────────────────────────────────────────────────────────
function pick(rnd,arr,n){const a=arr.slice();const out=[];n=Math.min(n,a.length);
 for(let i=0;i<n;i++){out.push(a.splice(Math.floor(rnd()*a.length),1)[0]);}return out;}

function makePaper(rnd,def,seq,ageDays,authPool){
 const len=def.titles.length;
 const variant=Math.floor(seq/len);
 const title=def.titles[seq%len]+(variant>0?' '+ROMAN[(variant-1)%ROMAN.length]:'');
 const lang=/[\u4e00-\u9fff]/.test(title)?'zh':'en';
 const id=(strHash(title+'|'+seq).toString(36)+'00000000').slice(0,8);
 const n_chunks=18+Math.floor(Math.pow(rnd(),1.6)*150);
 const ents=[];let eid=0;
 const add=(type,text,shared)=>{const e={id:'e'+(eid++),type,text,shared:!!shared};ents.push(e);return e;};
 pick(rnd,def.methods,2).forEach(m=>add('method',m));
 pick(rnd,def.materials,2).forEach(m=>add('material',m));
 if(def.dopants&&rnd()<0.5)add('dopant',def.dopants[Math.floor(rnd()*def.dopants.length)]);
 const params=pick(rnd,def.params,2+(rnd()<0.5?1:0));
 const rel=[];
 params.forEach(pm=>{
   const pe=add('parameter',pm);
   const u=PARAM_UNITS[pm];
   const dimless=(u==='');
   const ve=add('value',dimless?(rnd()*2).toFixed(2):(rnd()*120).toFixed(1));
   rel.push([pe.id,'has_value',ve.id]);
   if(!dimless){
     const ue=add('unit',u!==undefined?u:UNITS[Math.floor(rnd()*UNITS.length)]);
     rel.push([ve.id,'in_unit',ue.id]);
   }
 });
 const nf=2+(rnd()<0.4?1:0);
 for(let i=0;i<nf;i++)add('figure','Fig. '+(i+1));
 if(rnd()<0.5)add('table','Table 1');
 pick(rnd,def.claims,1+(rnd()<0.4?1:0)).forEach(c=>add('claim',c));
 if(rnd()<0.6)add('comparator',def.comparators[Math.floor(rnd()*def.comparators.length)]);
 pick(rnd,authPool,2+(rnd()<0.3?1:0)).forEach(a=>add('author',a));
 SHARED.filter(s=>s.c.indexOf(def.key)>=0&&rnd()<0.45)
   .slice(0,3).forEach(s=>add(s.type,s.t,true));
 // relations beyond param chains
 const by=t=>ents.filter(e=>e.type===t);
 const m0=by('method')[0],ma0=by('material')[0],cl0=by('claim')[0],fg0=by('figure')[0],cp0=by('comparator')[0];
 if(m0&&ma0)rel.push([m0.id,'applied_to',ma0.id]);
 if(cl0&&fg0)rel.push([cl0.id,'evidenced_by',fg0.id]);
 if(cp0&&ma0)rel.push([cp0.id,'compared_with',ma0.id]);
 const fi=pick(rnd,def.figs.map((c,i)=>i),2);
 const qs=pick(rnd,def.questions,2);
 // §sections — L2 drill structure: chunk shares + entity assignment by type
 const SEC_DEFS=[['Ⅰ','引言','INTRODUCTION'],['Ⅱ','方法','METHODS'],['Ⅲ','结果','RESULTS'],['Ⅳ','讨论','DISCUSSION']];
 const shr=[0.12+rnd()*0.05,0.26+rnd()*0.08,0.32+rnd()*0.08,0.16+rnd()*0.06];
 const ssum=shr.reduce((x,y)=>x+y,0);
 const sections=SEC_DEFS.map((s,i2)=>({num:s[0],zh:s[1],en:s[2],
  chunks:Math.max(2,Math.round(n_chunks*shr[i2]/ssum)),ents:[],q:null}));
 const SEC_OF={method:1,material:1,dopant:1,parameter:2,value:2,unit:2,figure:2,table:2,comparator:2,claim:3};
 ents.forEach(e=>{const si=SEC_OF[e.type];if(si!==undefined)sections[si].ents.push(e.id);});
 sections[0].q=qs[0]||null; sections[3].q=qs[1]||null;
 return {
  id,title,lang,cluster:def.idx,seq,
  keywords:pick(rnd,def.keywords,3),
  n_chunks,
  n_entities:ents.length,
  total_tokens:Math.round(n_chunks*(700+rnd()*500)),
  ingested_at:Date.now()-ageDays*86400000,
  entities:ents,relations:rel,
  questions:qs,sections,
  figures:fi.map((k,j)=>({id:'fig_'+(j+1),caption:def.figs[k]})),
  seed:strHash(id),x:0,y:0
 };
}

// ── layout helpers ──────────────────────────────────────────────────────────
function relax(papers,iters,minD){
 for(let it=0;it<iters;it++){
  for(let i=0;i<papers.length;i++)for(let j=i+1;j<papers.length;j++){
   const a=papers[i],b=papers[j];let dx=b.x-a.x,dy=b.y-a.y;
   let d2=dx*dx+dy*dy;if(d2>minD*minD)continue;
   let d=Math.sqrt(d2)||0.01;const push=(minD-d)/d*0.5;
   dx*=push;dy*=push;a.x-=dx;a.y-=dy;b.x+=dx;b.y+=dy;
  }
 }
}
function placePaper(rnd,p,c){
 const ang=rnd()*Math.PI*2,r=Math.pow(rnd(),0.6);
 p.x=c.cx+Math.cos(ang)*r*c.sx; p.y=c.cy+Math.sin(ang)*r*c.sy;
}

// ── link graph ──────────────────────────────────────────────────────────────
function buildLinks(papers){
 const map=new Map();
 papers.forEach((p,pi)=>{const seen=new Set();
  p.entities.forEach(e=>{const k=norm(e.text)+'|'+e.type;
   if(seen.has(k))return;seen.add(k);
   if(!map.has(k))map.set(k,[]);map.get(k).push(pi);});});
 const pair=new Map();
 map.forEach((list,k)=>{
  if(list.length<2||list.length>14)return;
  const text=k.split('|')[0];
  for(let i=0;i<list.length;i++)for(let j=i+1;j<list.length;j++){
   const pk=list[i]+'-'+list[j];
   if(!pair.has(pk))pair.set(pk,{a:list[i],b:list[j],w:0,texts:[]});
   const e=pair.get(pk);e.w++;if(e.texts.length<4)e.texts.push(text);
  }});
 const links=[...pair.values()].sort((a,b)=>b.w-a.w);
 const entIndex=new Map(); // norm text|type → {type,text,papers[]}
 map.forEach((list,k)=>{const [t,ty]=k.split('|');
  entIndex.set(k,{key:k,text:t,type:ty,papers:list});});
 return {links,entIndex};
}
function applyBudget(links,N,maxDeg){
 maxDeg=maxDeg||5;const deg={};const out=[];
 for(const l of links){
  if(out.length>=N)break;
  if((deg[l.a]||0)>=maxDeg||(deg[l.b]||0)>=maxDeg)continue;
  deg[l.a]=(deg[l.a]||0)+1;deg[l.b]=(deg[l.b]||0)+1;out.push(l);
 }
 return out;
}

// ── generate ────────────────────────────────────────────────────────────────
function generate(opts){
 const n=Math.max(1,opts.papers|0),k=Math.min(6,Math.max(3,opts.clusters|0));
 const rnd=mulberry32(opts.seed||7);
 const defs=CLUSTER_DEFS.slice(0,k).map((d,i)=>Object.assign({},d,{idx:i,hue:HUES[i]}));
 const wsum=defs.reduce((s,d)=>s+d.w,0);
 const spread=Math.max(1, Math.sqrt(n/70));   // big libraries breathe outwards
 const clusters=defs.map((d,i)=>{
  const a=(-90+i*360/k+(rnd()-0.5)*16)*Math.PI/180;
  const R=(330+rnd()*90)*spread;
  return Object.assign(d,{cx:Math.cos(a)*R,cy:Math.sin(a)*R,
   sx:(95+rnd()*55)*spread,sy:(80+rnd()*50)*spread,startAge:160+rnd()*260,
   authPool:pick(rnd,AUTHORS,5),count:0});
 });
 const papers=[];
 for(let i=0;i<n;i++){
  let r=rnd()*wsum,ci=0;
  for(let j=0;j<k;j++){r-=defs[j].w;if(r<=0){ci=j;break;}}
  const c=clusters[ci];
  let age=c.startAge*(0.06+0.94*Math.pow(rnd(),1.25));
  if(i===n-1)age=1.2;else if(i===n-2)age=3.4;else if(i===n-3)age=6.5;
  const p=makePaper(rnd,c,c.count++,age,c.authPool);
  placePaper(rnd,p,c);
  papers.push(p);
 }
 relax(papers,40,30);
 const {links,entIndex}=buildLinks(papers);
 return {papers,clusters,links,entIndex,seedRnd:rnd,
  lastVisit:Date.now()-5*86400000};
}

// ── live ingest (the "growth" demo) ─────────────────────────────────────────
function ingestOne(data){
 const rnd=data.seedRnd;
 const clusters=data.clusters;
 const ci=Math.floor(rnd()*clusters.length);
 const c=clusters[ci];
 const p=makePaper(rnd,c,c.count++,0.0007,c.authPool);
 placePaper(rnd,p,c);
 // local relaxation against neighbours only
 for(let it=0;it<24;it++){
  for(const q of data.papers){
   let dx=p.x-q.x,dy=p.y-q.y,d2=dx*dx+dy*dy;
   if(d2>900)continue;const d=Math.sqrt(d2)||0.01,push=(30-d)/d;
   p.x+=dx*push;p.y+=dy*push;
  }
 }
 data.papers.push(p);
 const rebuilt=buildLinks(data.papers);
 data.links=rebuilt.links;data.entIndex=rebuilt.entIndex;
 return p;
}

// ── L2 composition: fold param→value→unit chains into readable entries ───────
function composeSection(p,si){
 const sec=p.sections&&p.sections[si];
 if(!sec)return{items:[],hidden:0,q:null};
 const byId={};p.entities.forEach(e=>{byId[e.id]=e;});
 const inSec=new Set(sec.ents);
 const used=new Set();
 const items=[];
 for(const [s,pr,o] of p.relations){
  if(pr!=='has_value'||!inSec.has(s)||used.has(s))continue;
  let unit='';
  for(const [s2,p2,o2] of p.relations){
   if(p2==='in_unit'&&s2===o){unit=(byId[o2]||{}).text||'';used.add(o2);}
  }
  used.add(o);used.add(s);
  items.push({e:byId[s],label:byId[s].text+' = '+((byId[o]||{}).text||'?')+(unit?' '+unit:'')});
 }
 for(const id of sec.ents){
  if(used.has(id))continue;const e=byId[id];if(!e)continue;
  let label=e.text;
  if(e.type==='figure'){const m=/(\d+)/.exec(e.text);const fg=m&&p.figures[+m[1]-1];if(fg)label=e.text+' · '+fg.caption;}
  items.push({e,label});
 }
 const ORDER=['parameter','method','material','dopant','comparator','figure','table','claim'];
 items.sort((a,b)=>ORDER.indexOf(a.e.type)-ORDER.indexOf(b.e.type));
 const MAX=11;
 return {items:items.slice(0,MAX),hidden:Math.max(0,items.length-MAX),q:sec.q};
}

// ── REAL-DATA SEAM (for Claude Code) ───────────────────────────────
// To connect real lazy-paper exports, set window.GARDEN_EXPORT (before
// garden-app.js runs, or fetch + assign then call GardenApp.applyTweaks({}))
// with the shape documented in DATA_ADAPTER.md. adapt() maps it into the
// internal structure; positions, links and entIndex are computed here — the
// exporter does NOT need to provide any layout.
function adapt(exp){
 const rnd=mulberry32(7);
 const clusterDefs=(exp.clusters&&exp.clusters.length?exp.clusters:[{key:'all',en:'library',zh:'全部',paper_ids:null}])
  .slice(0,6).map((c,i)=>({key:c.key,en:c.en||c.key,zh:c.zh||c.key,idx:i,hue:HUES[i]}));
 const n=(exp.manifest&&exp.manifest.papers||[]).length;
 const spread=Math.max(1,Math.sqrt(n/70));
 const k=clusterDefs.length;
 const clusters=clusterDefs.map((d,i)=>{
  const a=(-90+i*360/k)*Math.PI/180, Rr=(330+rnd()*90)*spread;
  return Object.assign(d,{cx:Math.cos(a)*Rr,cy:Math.sin(a)*Rr,
   sx:(95+rnd()*55)*spread,sy:(80+rnd()*50)*spread,count:0});
 });
 const byCluster={};
 if(exp.clusters) exp.clusters.forEach((c,i)=>{(c.paper_ids||[]).forEach(id=>{byCluster[id]=Math.min(i,k-1);});});
 const papers=(exp.manifest.papers||[]).map(mp=>{
  const ents=(exp.entities&&exp.entities[mp.id]||[]).map(e=>({id:e.id,type:e.type,text:e.text}));
  const rels=(exp.relations&&exp.relations[mp.id])||[];
  let sections=(exp.sections&&exp.sections[mp.id])||null;
  if(!sections){
   const SECS=[['Ⅰ','引言','INTRODUCTION'],['Ⅱ','方法','METHODS'],['Ⅲ','结果','RESULTS'],['Ⅳ','讨论','DISCUSSION']];
   const SEC_OF={method:1,material:1,dopant:1,parameter:2,value:2,unit:2,figure:2,table:2,comparator:2,claim:3};
   sections=SECS.map((s,i)=>({num:s[0],zh:s[1],en:s[2],chunks:Math.max(2,Math.round((mp.n_chunks||20)/4)),ents:[],q:null}));
   ents.forEach(e=>{const si=SEC_OF[e.type];if(si!==undefined)sections[si].ents.push(e.id);});
  }
  const ci=byCluster[mp.id]!==undefined?byCluster[mp.id]:Math.floor(rnd()*k);
  const ing=typeof mp.ingested_at==='string'?Date.parse(mp.ingested_at):(mp.ingested_at||Date.now());
  return {id:mp.id,title:mp.title,lang:mp.lang||'en',cluster:ci,seq:clusters[ci].count++,
   keywords:mp.keywords||[],n_chunks:mp.n_chunks||20,n_entities:mp.n_entities||ents.length,
   total_tokens:mp.total_tokens||((mp.n_chunks||20)*900),ingested_at:ing,
   entities:ents,relations:rels,questions:mp.questions||[],
   figures:(mp.figures||[]).map((f,j)=>({id:f.id||('fig_'+(j+1)),caption:f.caption||''})),
   sections,seed:strHash(mp.id),x:0,y:0};
 });
 papers.forEach(p=>placePaper(rnd,p,clusters[p.cluster]));
 relax(papers,40,30);
 const {links,entIndex}=buildLinks(papers);
 return {papers,clusters,links,entIndex,seedRnd:rnd,
  lastVisit:Date.now()-5*86400000,fromExport:true};
}

return {generate,ingestOne,applyBudget,norm,composeSection,adapt,CLUSTER_DEFS,HUES};
})();
