import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const witnesses=JSON.parse(readFileSync(new URL('../fixtures/package02-financial-witnesses.json',import.meta.url),'utf8'));
const plain=x=>JSON.parse(JSON.stringify(x));
function context(extra={}) {const c={app:{registerExtension(){}},api:{},document:{querySelectorAll:()=>[]},queueMicrotask:fn=>fn(),...extra};vm.runInNewContext(source,c);return c;}

for(const width of [320,400,620,1000])test(`Classic native arrow safe content at ${width}px`,()=>{
 const c=context();class Native {static margin=17;static arrowMargin=7;static arrowWidth=12;}
 const options={values:['very long value']},item=Object.assign(new Native(),{name:'resolution',type:'combo',label:'A very long provider label',value:'very long value',options,y:20,height:20,labelBaseline:34,drawTruncatingText(){}});
 const n={size:[width,800],widgets:[item]};c.installParameterColumns(n);const rects=[],texts=[];
 const ctx={save(){},restore(){},beginPath(){},rect(...v){rects.push(v)},clip(){},measureText:t=>({width:t.length*8}),fillText(...v){texts.push(v)}};
 item.drawTruncatingText({ctx,width});const b=c.classicContentBounds(item,width);
 assert.equal(b.left,40);assert.equal(b.right,width-40);assert(rects[0][0]+rects[0][2]<rects[1][0]);assert.equal(rects[1][0]+rects[1][2],width-40);
 assert.equal(item.options,options);assert.equal(item.value,'very long value');assert.equal(n.widgets[0],item);
 for(const [text,x] of texts)assert(x>=40 && x<=width-40);
 assert(c.fitWidgetText(ctx,'長い provider label',30).endsWith('…'));
});

test('Classic trusted native capture keeps handle ownership and isolates deferred notifications',()=>{
 const handlers={},phases={},frames=[],micro=[];let n;
 const canvas={addEventListener:(name,fn,capture)=>{handlers[name]=fn;phases[name]=capture;},removeEventListener:(name)=>delete handlers[name]};
 const c=context({queueMicrotask:fn=>micro.push(fn),requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},cancelAnimationFrame(){}});
 c.app.canvas={canvas,graph:{getNodeById:()=>n},convertEventToCanvasOffset:()=>[77,88],pointer:{}};
 n={id:3,pos:[11,12],size:[400,600],widgets:[{name:'prompt',value:'saved',options:{}}],findResizeDirection:(x,y)=>{assert.deepEqual([x,y],[77,88]);return 'SE';},computeSize:()=>[400,300],setDirtyCanvas(){}};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);
 assert.equal(phases.pointerdown,true);assert.equal(phases.pointermove,true);handlers.pointerdown({isTrusted:true,button:0,pointerId:8});
 for(const [width,height] of [[610,900],[450,700],[320,300],[610,920]]){
  const e={isTrusted:true,pointerId:8};handlers.pointermove(e);c.app.canvas.pointer.eMove=e;n.size=[width,height];n.onResize(n.size);
  assert.equal(n.__orvPreferredWidth,width);const budget=n.__orvMasterPromptHeight;
  n.size=[999,1999];n.onResize(n.size);assert.equal(n.__orvPreferredWidth,width);assert.equal(n.__orvMasterPromptHeight,budget);
  while(micro.length)micro.shift()();while(frames.length)frames.shift()();
 }
 handlers.pointerup();assert.equal(n.__orvUserResizeActive,false);assert.deepEqual(n.pos,[11,12]);assert.equal(n.widgets[0].value,'saved');
 n.onRemoved();assert.equal(Object.keys(handlers).length,0);
});

test('native cached badge is cloned: pack hidden, IDs/lifecycle and unrelated nodes intact',()=>{
 const c=context(),cached={text:'#7 OpenRouter-Video BETA',color:'green'},callback=()=>cached,n={badges:[callback]};
 c.suppressPackageBadge(n);const wrapped=n.badges[0],out=wrapped();assert.notEqual(out,cached);assert.equal(cached.text,'#7 OpenRouter-Video BETA');assert.equal(out.text,'#7  BETA');assert.equal(out.color,'green');
 c.suppressPackageBadge(n);assert.equal(n.badges[0],wrapped);const other={badges:[callback]};assert.equal(other.badges[0](),cached);
 const leaf={textContent:'OpenRouter-Video',childElementCount:0,style:{},closest:()=>null},footer={textContent:'OpenRouter-Video',style:{},querySelector:()=>null};const root={querySelectorAll:()=>[leaf]};leaf.parentElement=footer;footer.parentElement=root;
 c.suppressPackageBadge(n,root);assert.equal(footer.style.display,'none');assert.equal(leaf.style.display,undefined);
});

test('compact multiline native padding does not consume elastic budget or values',()=>{
 const c=context(),fields=['prompt','provider_option:p:negative'].map((name,i)=>({name,label:name,value:'line\ntext',element:{style:{}},options:{margin:10},...(i?{__orvTextSemantic:'negative_prompt'}:{})}));
 const n={size:[400,800],widgets:fields,__orvMasterPromptHeight:304};c.sizePrimaryControls(n);const before=c.textRegionGeometry(n);c.stylePrompt(n);
 assert.equal(c.textRegionGeometry(n).budget,before.budget);assert.equal(fields[0].computeSize()[1],fields[1].computeSize()[1]);
 for(const w of fields){assert.equal(w.options.margin,0);assert.equal(w.element.style.padding,'4px 6px');assert.equal(w.element.style.boxSizing,'border-box');assert.equal(w.element.style.lineHeight,'18px');assert.equal(w.value,'line\ntext');}
 for(const name of ['model','inference_method','resolution','aspect_ratio','duration']){const item={name,options:{}};c.sizePrimaryControls({widgets:[item]});assert.equal(item.computeSize()[1],20);}
});

test('semantic colon is display only; API method and model identifiers unchanged',()=>{
 const c=context();assert.equal(c.modelDisplayLabel('Vendor — Model'),'Vendor: Model');assert.equal(c.modelDisplayLabel('Vendor: Model'),'Vendor: Model');
 for(const method of ['T2V','I2V','FLF2V','IR2V','MI2V','VR2V','AR2V','MMR2V','V2V_EDIT','V2V_EXTEND','V2V_UPSCALE']){
  const label=vm.runInNewContext(`METHOD_LABELS[${JSON.stringify(method)}]`,c);assert(label.includes(': '),method);assert(!label.includes(' — '),method);
 }
});

for(const locale of ['en','ru'])for(const [key,{request,result}] of Object.entries(witnesses))test(`actual backend ${key} precompletion UI ${locale}`,()=>{
 const c=context();c.app.ui={settings:{getSettingValue:()=>locale}};const r=plain(result),n={widgets:Object.entries(request).map(([name,value])=>({name,value})),__orvEstimate:{result:r}};
 const advisory=c.costPrecompletionAdvisory(r);assert(advisory,key);assert.equal(r.state,'INVALID');assert.equal(r.amount_usd,null);assert.equal(c.costPriceView(r).accent,'#9E6BFF');
 const view=c.costTooltipView(n);assert(view.note.length>0);assert(!view.note.includes('undefined'));assert(view.sections.length>0);
 if(key==='video'){assert.match(c.costPriceView(r).badge,/RATE/);assert.equal(advisory.display,'RATE_ONLY');}
 else assert.match(c.costPriceView(r).badge,/REF\./);
 assert.equal(r.precompletion_advisory.actual_reference_kinds.length,0);
});

for(const mutation of ['null_missing','null_alternative','negative_rate','invalid_scope','primary_total','hard_invalid','stale','no_rates_hash'])test(`additive advisory fails closed: ${mutation}`,()=>{
 const c=context(),r=plain(witnesses.fixed.result),a=r.precompletion_advisory;
 if(mutation==='null_missing')a.missing_inputs=[null];
 if(mutation==='null_alternative')a.alternatives=[null];
 if(mutation==='negative_rate'){a.display='RATE_ONLY';a.scenarios=[];a.amount_usd=null;a.rates=[{rate_usd:'-1',rate_unit:'s',assumption:'invalid'}];}
 if(mutation==='invalid_scope')a.scope='TOTAL';if(mutation==='primary_total')r.amount_usd='1';if(mutation==='hard_invalid')r.reason='media_duration_exceeds_limit';if(mutation==='stale')r.valid_for_ms=0;if(mutation==='no_rates_hash')r.rates_hash=null;
 assert.doesNotThrow(()=>c.costPrecompletionAdvisory(r));assert.equal(c.costPrecompletionAdvisory(r),null);
});
