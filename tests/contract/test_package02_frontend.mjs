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
 assert.equal(phases.pointerdown,true);assert.equal(phases.pointermove,true);c.app.canvas.pointer.onDrag=e=>n.onResize(n.size);handlers.pointerdown({isTrusted:true,button:0,pointerId:8});
 for(const [width,height] of [[610,900],[450,700],[320,300],[610,920]]){
  const e={isTrusted:true,pointerId:8};handlers.pointermove(e);c.app.canvas.pointer.eMove=e;n.size=[width,height];c.app.canvas.pointer.onDrag(e);
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


test('Classic native drag survives the real capture-to-target microtask checkpoint and rejects deferred notifications',()=>{
 const handlers={},micro=[];let n;
 const c=context({queueMicrotask:fn=>micro.push(fn),requestAnimationFrame:()=>1});
 c.app.canvas={canvas:{addEventListener:(name,fn)=>handlers[name]=fn,removeEventListener(){}},graph:{getNodeById:()=>n},convertEventToCanvasOffset:()=>[390,590],pointer:{}};
 n={id:5,size:[400,600],widgets:[{name:'prompt',options:{}}],computeSize:()=>[400,300],findResizeDirection:()=> 'SE'};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);
 c.app.canvas.pointer.onDrag=e=>{n.size=[620,900];n.onResize(n.size);};
 handlers.pointerdown({isTrusted:true,button:0,pointerId:9});
 const e={isTrusted:true,pointerId:9};handlers.pointermove(e);
 // Browsers run a microtask checkpoint after each listener, before the native bubble handler.
 while(micro.length)micro.shift()();c.app.canvas.pointer.eMove=e;c.app.canvas.pointer.onDrag(e);
 assert.equal(n.__orvPreferredWidth,620);
 const height=n.__orvMasterPromptHeight;n.size=[999,1999];n.onResize(n.size);
 assert.equal(n.__orvPreferredWidth,620);assert.equal(n.__orvMasterPromptHeight,height);
 handlers.pointerup();
});


test('Nodes2 native DIV pack badge is hidden with its empty footer, but widget content remains',()=>{
 const c=context(),footer={textContent:'OpenRouter-Video ',style:{},querySelector:()=>null},leaf={childElementCount:0,textContent:'OpenRouter-Video ',style:{},closest:()=>null,parentElement:footer};
 const root={querySelectorAll:selector=>selector.includes('div')?[leaf]:[]};footer.parentElement=root;
 c.suppressPackageBadge({},root);assert.equal(footer.style.display,'none');
 const inputLeaf={...leaf,closest:()=>({})};footer.style={};root.querySelectorAll=()=>[inputLeaf];c.suppressPackageBadge({},root);assert.equal(footer.style.display,undefined);
});

const nativePartialComponent={"availability":"UNAVAILABLE","state":"PARTIAL","observed_at":"2026-11-24T17:40:40.960593+00:00","applied_skus":["video_tokens_without_audio"],"amount_usd":null,"lower_usd":null,"upper_usd":null,"range_kind":null,"planning":null,"precompletion_advisory":null,"validation_details":[],"valid_for_ms":283766,"rate_usd":null,"rate_unit":null,"breakdown":[{"sku":"video_tokens_without_audio","unit":"USD","quantity":"86400","rate_usd":"0.0000107","amount_usd":"0.9244800","relation":"base","evidence":"https://openrouter.ai/blog/insights/seedance-2-5-review/","applicability":"APPLICABLE"}],"assumptions":["Advisory continuous formula; provider billing may differ."],"reason_codes":["unclassified_pricing_sku"],"snapshot_hash":null,"rates_hash":"1b1c8d71c10f103eb46aa2af8ba16319340b96e645baf8a31076b899cb746e33","rules_version":"ACI-1.0","context_revision":1,"reason":"unclassified_pricing_sku"};

for(const locale of ['en','ru'])test(`known partial component remains visible without claiming a total ${locale}`,()=>{
 const c=context();c.app.ui={settings:{getSettingValue:()=>locale}};const r=plain(nativePartialComponent),n={widgets:[{name:'model',value:'bytedance/seedance-2.5'},{name:'inference_method',value:'MI2V'},{name:'resolution',value:'720p'},{name:'aspect_ratio',value:'16:9'},{name:'duration',value:4}],__orvEstimate:{result:r}};
 const view=c.costPriceView(r);assert.equal(view.kind,'component');assert.equal(view.accent,'#9E6BFF');assert.match(view.badge,locale==='ru'?/0,92 REF/:/0\.92 REF/);assert.equal(r.amount_usd,null);assert.equal(r.state,'PARTIAL');
 const tip=c.costTooltipView(n);assert(tip.context.includes('720p'));assert(tip.context.includes('4'));assert(tip.note.includes(c.costText('componentNote')));assert(tip.note.includes(c.costText('modelNote')));
 for(const change of ['stale','invalid','unknown','no_hash','ambiguous','unsupported','discount','negative']){
  const bad=plain(r);if(change==='stale')bad.valid_for_ms=0;if(change==='invalid')bad.state='INVALID';if(change==='unknown')bad.state='UNKNOWN';if(change==='no_hash')bad.rates_hash=null;
  if(change==='ambiguous')bad.breakdown.push({...bad.breakdown[0]});if(change==='unsupported')bad.breakdown[0].applicability='UNVERIFIED';if(change==='discount')bad.breakdown[0].relation='discount';if(change==='negative')bad.breakdown[0].amount_usd='-1';
  assert.equal(c.costAdvisoryComparison(bad),null,change);
 }
});

for(const nested of [false,true])test(`Nodes2 readonly duration preserves native label and restores input layout nested=${nested}`,()=>{
 const el=(kind='')=>({kind,style:{},children:[],setAttribute(){},append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}},contains(n){return this===n||this.children.some(c=>c.contains(n));},remove(){this.parentElement.children=this.parentElement.children.filter(c=>c!==this);},querySelector(selector){const all=[];const walk=n=>{all.push(n);n.children.forEach(walk);};this.children.forEach(walk);return all.find(n=>selector==='input'?n.kind==='input':selector==='.orv-duration-readonly'?n.className==='orv-duration-readonly':selector==='[data-testid="widget-layout-field-label"]'?n.kind==='label':false)||null;}});
 const input=el('input');input.getAttribute=()=> 'duration';const label=el('label');label.textContent='Длительность';
 const field=el(),cell=el(),row=el();field.append(input);
 if(nested){cell.append(label,field);row.append(cell);}else{cell.append(input);row.append(label,cell);}
 const c=context({document:{createElement:()=>el()}}),item={name:'duration',value:8,options:{read_only:true},__orvDurationAdapter:true,__orvDurationPresentation:'FIXED'},node={widgets:[item]},root={};
 c.syncReadOnlyDurationRow(node,root,row);const display=row.querySelector('.orv-duration-readonly');
 assert(display);assert.notEqual(label.style.display,'none');assert.notEqual((nested?cell:row).style.display,'none');
 assert.equal((nested?field:cell).style.display,'none');assert.equal(display.parentElement,nested?cell:row);assert.equal(display.style.gridColumn,nested?'2 / -1':'3 / -1');
 assert.equal(display.children[0].textContent,'8 s');c.syncReadOnlyDurationRow(node,root,row);assert.equal(row.querySelector('.orv-duration-readonly'),display);
 item.options.read_only=false;c.syncReadOnlyDurationRow(node,root,row);assert.equal((nested?field:cell).style.display,'');assert.equal(row.querySelector('.orv-duration-readonly'),null);assert.equal(input.value,undefined);assert.equal(item.value,8);
});

for(const locale of ['en','ru'])for(const selectedDuration of [4,-1])test(`reference billing seconds do not replace selected output duration ${locale} ${selectedDuration}`,()=>{
 const c=context();c.app.ui={settings:{getSettingValue:()=>locale}};
 // Presentation witness matching the native Wan mixed-input shape; not a tariff fixture.
 const result={state:'UNKNOWN',planning:{version:'ACI-PLANNING-1',display:'DETAIL_ONLY',scenarios:[{scope:'COMPARISON',sku:'duration_seconds',quantity:'16.066016',quantity_unit:'s',amount_usd:'1.6066016',assumption:'Reference billing quantity includes input and output seconds.'}]}};
 const n={widgets:[{name:'model',value:'alibaba/wan-3.0'},{name:'inference_method',value:'MMR2V'},{name:'resolution',value:'720p'},{name:'aspect_ratio',value:'16:9'},{name:'duration',value:selectedDuration}],__orvEstimate:{result}};
 const before=JSON.stringify(result),tip=c.costTooltipView(n);assert(tip.context.includes('720p'));assert(!tip.context.includes('16.066016'));assert(!tip.context.includes('16,066016'));
 assert(tip.context.includes(selectedDuration===-1?c.costText('automatic'):'4'));
 const basis=tip.sections.find(s=>s.title===c.costText('referenceScope'));assert(basis);assert.equal(basis.rows[0][0],c.costText('billableQuantity'));assert.equal(basis.rows[0][1],locale==='ru'?'16,066016 с':'16.066016s');
 assert.equal(tip.amount,locale==='ru'?'$1,61':'$1.61');assert.equal(JSON.stringify(result),before);assert.equal(n.widgets[4].value,selectedDuration);
});

for(const completion of ['pointerup','pointercancel'])test(`Classic completion survives native bubble suppression: ${completion}`,()=>{
 const listeners=new Map();let n;
 const canvas={addEventListener:(name,fn,capture=false)=>listeners.set(name,{fn,capture}),removeEventListener:(name,fn,capture=false)=>{const prior=listeners.get(name);assert.equal(prior.fn,fn);assert.equal(prior.capture,capture);listeners.delete(name);}};
 const c=context();c.app.canvas={canvas,graph:{getNodeById:()=>n},pointer:{},convertEventToCanvasOffset:()=>[0,0]};
 n={id:4,size:[400,600],widgets:[{name:'prompt',value:'preserved',options:{}}],findResizeDirection:()=> 'SE',computeSize:()=>[400,300],setDirtyCanvas(){}};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);
 const native=e=>n.onResize(n.size);c.app.canvas.pointer.onDrag=native;
 listeners.get('pointerdown').fn({isTrusted:true,button:0,pointerId:1});const e={isTrusted:true,pointerId:1};c.app.canvas.pointer.eMove=e;n.size=[620,800];c.app.canvas.pointer.onDrag(e);
 const master=n.__orvMasterPromptHeight;assert.equal(n.__orvUserResizeActive,true);
 // Native target handling can suppress later bubble listeners. Capture still runs.
 const end=listeners.get(completion);if(end.capture)end.fn(e);
 assert.equal(n.__orvUserResizeActive,false);assert.equal(c.app.canvas.pointer.onDrag,native);assert.equal(n.__orvLiveSize,undefined);assert.equal(n.__orvMasterPromptHeight,master);assert.equal(n.widgets[0].value,'preserved');
 n.onRemoved();assert.equal(listeners.size,0);
});

test('unknown numeric Auto never displays native coerced zero or overlaps the absolute input',()=>{
 const state={style:{},setAttribute(){},addEventListener(){}},outer={append(e){this.state=e;},querySelector(){return this.state||null;}},inner={parentElement:outer,append(){throw new Error('state must not overlap absolute input');}},doc={activeElement:null};
 const input={value:'0',ownerDocument:doc,parentElement:inner,getAttribute:()=> 'provider_option:test::stability'};
 const item={name:'provider_option:test::stability',type:'number',label:'Stability',value:null,__orvProviderOption:true,__orvProviderAuto:true,__orvProviderKnownDefault:false};
 const c=context({document:{createElement:()=>state},getComputedStyle:()=>({position:'absolute'})}),row={querySelector:s=>s==='input'?input:null},n={widgets:[item]};
 c.syncProviderNumericState(n,row);assert.equal(input.value,'');assert.equal(input.placeholder,'Auto');assert.equal(state.hidden,true);assert.equal(outer.state,state);assert.equal(item.value,null);
 // A focused native editor owns its uncommitted draft.
 doc.activeElement=input;input.value='0.4';c.syncProviderNumericState(n,row);assert.equal(input.value,'0.4');assert.equal(item.value,null);
 // Explicit zero stays visible, with a reset; it never becomes omission.
 item.__orvProviderAuto=false;item.value=0;input.value='0';c.syncProviderNumericState(n,row);assert.equal(input.value,'0');assert.equal(state.hidden,false);assert.equal(state.textContent,'↺');assert.equal(item.value,0);
 // A documented default remains a value plus one compact Auto state.
 doc.activeElement=null;item.__orvProviderAuto=true;item.__orvProviderKnownDefault=true;item.value=1;input.value='1';c.syncProviderNumericState(n,row);assert.equal(input.value,'1');assert.equal(state.hidden,false);assert.equal(state.textContent,'Auto');assert.equal(item.value,1);
});

test('Vue observer ignores unrelated DOM and batches only affected nodes per frame',()=>{
 const frames=[], synced=[];
 let notify;
 const first={id:1},second={id:2};
 const c=context({
  document:{head:{append(){}},body:{},createElement:()=>({})},
  MutationObserver:class {constructor(callback){notify=callback;}observe(){}},
  requestAnimationFrame:callback=>frames.push(callback),
 });
 c.app.graph={getNodeById:id=>String(id)==='1'?first:second};
 c.syncBetaPresentation=node=>synced.push(node.id);
 c.installBetaPresentation(first);c.installBetaPresentation(second);
 assert.equal(frames.length,1);
 frames.shift()();
 assert.deepEqual(synced.splice(0),[1,2]);
 const outside={target:{},addedNodes:[{matches:()=>false,querySelector:()=>null}],removedNodes:[]};
 notify([outside]);
 assert.equal(frames.length,0);
 const inside={target:{closest:()=>({dataset:{nodeId:'1'}})},addedNodes:[],removedNodes:[]};
 notify([inside]);notify([inside,outside]);
 assert.equal(frames.length,1);
 frames.shift()();
 assert.deepEqual(synced.splice(0),[1]);
 notify([{...outside,addedNodes:[{matches:()=>true}]}]);
 frames.shift()();
 assert.deepEqual(synced,[1,2]);
});
