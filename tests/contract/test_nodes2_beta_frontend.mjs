import { reviewedRcText } from "./rc_reviewed_patch.mjs";
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import test from 'node:test';
const root=new URL('../../',import.meta.url);
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
function context(extra={}){const c={app:{registerExtension(){}},api:{},...extra};vm.runInNewContext(source,c);return c;}
test('visibility dialects agree without changing saved state',()=>{
 const c=context();for(const name of ['REFERENCES','STATE','Advanced','first_frame_url','last_frame_url']){const w={name,value:'saved legacy value',options:{advanced:true},__orvComputeSize:()=>[0,20],serialize:true};const initialOptions=w.options;c.setVisible(w,false);assert.equal(w.options,initialOptions);assert.equal(w.hidden,true);assert.equal(w.options.hidden,true);assert.equal(w.computeSize()[1],-4);assert.equal(w.value,'saved legacy value');assert.equal(w.serialize,true);c.setVisible(w,true);assert.equal(w.options.hidden,false);assert.equal(w.computeSize()[1],20);}
});
test('geometry owns Size visibility while workflow control remains primary',()=>{
 const c=context();const n={widgets:[{name:'size',hidden:true,options:{advanced:false}},{name:'randomize',label:'control after generate',hidden:true,options:{advanced:true}}]};c.syncAdvancedControls(n);assert.equal(n.widgets[0].hidden,true);assert.equal(n.widgets[1].hidden,false);
});
test('estimate is plain presentation state, no COST widget or serializer slot',()=>{
 const c=context();const state=c.createEstimateState();state.value='≈ $1.60 EST.';assert.equal(state.value,'≈ $1.60 EST.');assert.equal(state.type,undefined);assert.equal(state.serializeValue,undefined);assert.ok(!source.includes('addReadOnlyWidget(\n                this,\n                "COST"'));assert.ok(source.includes('this.__orvEstimate = createEstimateState()'));
});
function geometryStyle(native={}) {
 const tokens=new Map();
 return {...native,getPropertyValue(key){return tokens.get(key) ?? native.getPropertyValue?.(key) ?? '';},
  setProperty(key,value){tokens.set(key,value);},removeProperty:key=>tokens.delete(key)};
}
function domFixture(){
 const marks=[];const textarea={rows:5,placeholder:''};const plain={querySelector(){return null;},classList:{add(){}}};const prompt={querySelector(s){return s==='textarea'?textarea:s==='label[for]'?{textContent:'prompt',style:{}}:null;},toggleAttribute(key,on){if(on)marks.push(key);}};
 const grid={style:{},querySelectorAll(){return [plain,plain,prompt,plain,plain,plain,plain,plain,plain];}};
 const header={children:[],querySelector(){return this.children[0];},append(x){this.children.push(x);}};
 const element={dataset:{nodeId:'22'},style:geometryStyle(),attrs:new Map(),getAttribute(k){return this.attrs.get(k)},setAttribute(k,v){this.attrs.set(k,v)},removeAttribute(k){this.attrs.delete(k)},classList:{add(s){marks.push(s);},remove(s){const i=marks.indexOf(s);if(i>=0)marks.splice(i,1);}},querySelector(s){return s.startsWith('.lg-node-header')?header:grid;}};
 const document={querySelectorAll(){return [element];},createElement(){return {style:{},textContent:'',title:'',setAttribute(name,value){this[name]=value;},addEventListener(){}};}};
 const c=context({document});const n={id:22,widgets:[{name:'prompt',label:'prompt'}],__orvEstimate:{value:'≈ $1.60 EST.'}};return {c,n,header,grid,textarea,marks,element};
}

test('absolute native Vue root measures intrinsic flow, negative footer margin and Canvas title offset',()=>{
 const {c,n}=domFixture(),root=c.document.querySelectorAll()[0],grid=root.querySelector('[data-testid="node-widgets"]');
 const block=height=>({children:[],css:{display:'block',position:'static'},getBoundingClientRect:()=>({height,width:400})});
 const header=block(30),footer=block(40),overlay=block(900);footer.css.marginTop='-20px';overlay.css.position='absolute';
 grid.css={display:'grid',position:'static'};grid.getBoundingClientRect=()=>({height:200,width:400});
 const wrapper={children:[header,grid,footer],css:{display:'flex',flexDirection:'column',position:'static'},getBoundingClientRect:()=>({width:400,height:999})};
 root.children=[overlay,wrapper];root.css={display:'flex',flexDirection:'column',position:'absolute'};root.getBoundingClientRect=()=>({width:400,height:999});
 c.getComputedStyle=e=>({display:'block',position:'static',minHeight:'0px',...e.css});
 n.size=[400,800];n.pos=[11,12];n.boundingOffset=[0,30];n.__orvMasterPromptHeight=100;n.computeSize=()=>[400,400];n.setSize=size=>{n.size=size;};
 assert.equal(c.nativeFlowHeight(root,1),250);c.syncBetaPresentation(n);
 assert.equal(n.__orvNativeFixedHeight,120);assert.equal(n.size[1],220);assert.equal(n.__orvMasterPromptHeight,100);assert.deepEqual(n.pos,[11,12]);
 grid.getBoundingClientRect=()=>({height:300,width:400});c.syncBetaPresentation(n);assert.equal(n.size[1],320);assert.equal(n.__orvMasterPromptHeight,100);
 grid.getBoundingClientRect=()=>({height:200,width:400});c.syncBetaPresentation(n);assert.equal(n.size[1],220);
});
test('Beta estimate is one header child, updates unavailable, never body overlay',()=>{
 const {c,n,header}=domFixture();c.syncBetaPresentation(n);c.syncBetaPresentation(n);assert.equal(header.children.length,1);assert.equal(header.children[0].textContent,'≈ $1.60 EST.');n.__orvEstimate.value='ESTIMATE UNAVAILABLE';c.syncBetaPresentation(n);assert.equal(header.children.length,1);assert.equal(header.children[0].title,'');assert.ok(header.children[0]['aria-label']);assert.equal(header.children[0].role,'button');assert.equal(header.children[0].tabIndex,0);assert.ok(!source.includes('position:absolute'));
});
test('native Vue grid rewrites cannot replace OpenRouter prompt or column geometry',()=>{
 const {c,n,grid,textarea,element}=domFixture();c.syncBetaPresentation(n);
 assert.equal(element.style.getPropertyValue('--orv-prompt-height'),'42px');
 grid.style.gridTemplateRows='min-content auto';grid.style.flex='1';
 element.className='host-selected';
 assert.equal(element.getAttribute('data-orv-layout'),'generate');
 c.syncBetaPresentation(n);
 assert.equal(element.className,'host-selected');
 assert.equal(grid.style.gridTemplateRows,'min-content auto');assert.equal(grid.style.flex,'1');
 assert.equal(element.style.getPropertyValue('--orv-prompt-height'),'42px');assert.equal(textarea.rows,2);
 assert(source.includes('grid-template-rows:none !important'));
 assert(source.includes('height:var(--orv-prompt-height,42px)'));
});
test('Classic canvas remains untouched when Vue DOM is absent',()=>{
 const c=context({document:{querySelectorAll:()=>[]}});assert.doesNotThrow(()=>c.syncBetaPresentation({id:22}));
});

test('PUX03 advanced textareas never compete with Prompt for flexible height',()=>{
 const {c,n,grid}=domFixture(),marks=[];
 const advanced={rows:5,placeholder:'negative_prompt'},promptArea={rows:2,placeholder:'Prompt'};
 const row=(area)=>({querySelector(s){return s==='textarea'?area:s==='label[for]'&&area===promptArea?{textContent:'prompt',style:{}}:null;},toggleAttribute(key,on){if(on)marks.push([area.placeholder,key]);}});
 grid.querySelectorAll=()=>[row(advanced),row(promptArea),row({rows:3,placeholder:'provider notes'})];
 c.syncBetaPresentation(n);assert.equal(c.document.querySelectorAll()[0].style.getPropertyValue('--orv-prompt-height'),'42px');
 assert.equal(advanced.rows,5);assert.deepEqual(marks,[['Prompt','data-orv-creative-layout']]);
 grid.querySelectorAll=()=>[row(advanced)];c.syncBetaPresentation(n);assert.equal(grid.style.flex,undefined);
});

test('PUX03 v1.1 shared column budget is bounded independently of labels and values',()=>{
 const {c,n,grid}=domFixture();n.size=[400,600];n.__orvMasterPromptHeight=224;
 for(const [width,label] of [[320,112],[400,128],[1000,160]]){
   n.size[0]=width;c.syncBetaPresentation(n);assert.equal(c.document.querySelectorAll()[0].style.getPropertyValue('--orv-label-width'),`${label}px`);
   assert.equal(c.document.querySelectorAll()[0].style.getPropertyValue('--orv-prompt-height'),'224px');
 }
});

test('PUX03 v1.1 native resize gesture is explicit; untrusted/layout events do not own geometry',()=>{
 const {c,n,grid}=domFixture(),root=c.document.querySelectorAll()[0],handlers={},frames=[],microtasks=[];
 root.style=geometryStyle({getPropertyValue:key=>key==='--node-width'?'610px':'930px'});root.getBoundingClientRect=()=>({width:400,height:830});root.addEventListener=(name,fn)=>handlers[name]=fn;c.requestAnimationFrame=fn=>frames.push(fn);c.queueMicrotask=fn=>microtasks.push(fn);
 n.size=[400,800];n.__orvMasterPromptHeight=120;n.computeSize=()=>[320,400];c.installResponsiveHeight(n);c.syncBetaPresentation(n);const initialBudget=n.__orvMasterPromptHeight;
 handlers.pointerdown({isTrusted:false,button:0,target:{closest:()=>({})}});assert(!n.__orvUserResizeActive);
 handlers.pointerdown({isTrusted:true,button:0,target:{closest:()=>null}});assert(!n.__orvUserResizeActive);
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:1,target:{closest:()=>({dataset:{corner:'SE'}})}});assert.equal(n.__orvUserResizeActive,true);handlers.gotpointercapture({isTrusted:true,pointerId:1});
 assert.equal(root.style.getPropertyValue('--orv-prompt-height'),`${initialBudget}px`);
 handlers.gotpointercapture({isTrusted:true,pointerId:1});handlers.pointermove({isTrusted:true,pointerId:1});microtasks.shift()();n.size=[777,1777];n.onResize(n.size);assert.equal(n.__orvPreferredWidth,610);assert.equal(n.__orvMasterPromptHeight,initialBudget+100);n.size=[555,1400];handlers.lostpointercapture();while(frames.length)frames.shift()();
 assert.equal(n.__orvPreferredWidth,610);assert.equal(n.__orvMasterPromptHeight,initialBudget+100);assert.equal(n.__orvUserResizeActive,false);
 assert.equal(root.style.getPropertyValue('--orv-prompt-height'),`${initialBudget+100}px`);
 const replacement={...n,size:[400,700],__orvUserResizeActive:false};c.syncBetaPresentation(replacement);
 assert.equal(root.__orvGeometryOwner,replacement);assert.equal(n.__orvUserResizeActive,false);
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:1,target:{closest:()=>({dataset:{corner:'SE'}})}});
 assert.equal(replacement.__orvUserResizeActive,true);assert.equal(n.__orvUserResizeActive,false);
});

test('PUX03 v1.1 Classic bounded cells retain native values, options and widget identity',()=>{
 const c=context(),options={values:['one','two']},item={name:'provider.long.parameter',type:'combo',label:'Long provider parameter',value:'two',options,y:20,height:20,labelBaseline:35,drawTruncatingText(){}};
 const node={size:[400,600],widgets:[item]};c.installParameterColumns(node);const rectangles=[],texts=[];
 const ctx={save(){},restore(){},beginPath(){},rect(...args){rectangles.push(args)},clip(){},fillText(...args){texts.push(args)}};
 item.drawTruncatingText({ctx,width:400});assert.equal(rectangles[0][0],35);assert.equal(rectangles[0][2],128);assert.equal(rectangles[1][0],171);assert.equal(rectangles[1][0]+rectangles[1][2],365);
 assert.equal(texts[0][0],'Long provider parameter');assert.equal(texts[1][0],'two');assert.equal(item.options,options);assert.equal(item.value,'two');assert.equal(node.widgets[0],item);
});

test('final review Resume has cost disclosure without Generate geometry or listeners',()=>{
 const {c,n,header,grid}=domFixture(),root=c.document.querySelectorAll()[0],handlers={};
 root.style=geometryStyle({minWidth:'217px'});root.addEventListener=(name,fn)=>handlers[name]=fn;root.removeEventListener=name=>delete handlers[name];
 const label={style:{maxWidth:'81px'},textContent:'Native label',title:'Native hint'},row={style:{gridColumn:'native'},querySelector:s=>s==='[data-testid="widget-layout-field-label"]'?label:null};
 grid.querySelectorAll=()=>[row];
 n.__orvResumeActualInstalled=true;c.syncBetaPresentation(n);
 assert.equal(root.style.minWidth,'217px');assert.equal(Object.keys(handlers).length,0);assert.equal(root.__orvGeometryOwner,undefined);
 assert.equal(header.children.length,1);assert.equal(grid.style.gridTemplateColumns,undefined);
 n.__orvResumeActualInstalled=false;c.syncBetaPresentation(n);assert(root.style.getPropertyValue('--orv-label-width'));
 n.__orvResumeActualInstalled=true;c.syncBetaPresentation(n);assert.equal(root.style.minWidth,'217px');assert.equal(Object.keys(handlers).length,0);
 assert.equal(root.getAttribute('data-orv-layout'),'resume');assert.equal(root.style.getPropertyValue('--orv-label-width'),'');assert.equal(label.style.maxWidth,'81px');assert.equal(label.title,'Native hint');assert.equal(row.style.gridColumn,'native');
});
function capacityFixture(n,c){
 c.app.graph={links:{},getNodeById:id=>({outputs:[{type:["IMAGE","IMAGE","VIDEO","AUDIO"][id-1]}]})};
 n.__orvCapability={__methodProfile:{topology:{reference_kinds:['image','video','audio'],max:50,per_kind_max:{image:30,video:10,audio:10}}}};
 n.inputs=['IMAGE','IMAGE','VIDEO','AUDIO'].map((type,i)=>({name:`direct_references.reference_${i}`,type,link:i+1}));
 n.inputs.forEach((item,i)=>c.app.graph.links[item.link]={origin_id:i+1,origin_slot:0});
 n.properties={orv_capability_intent:{media:[{active_name:null},{active_name:null}]}};
}
test('PUX05 structured capacity preserves active quantities, independent caps and unknowns',()=>{
 const c=context(),n={__orvReferenceSummary:'deliberately stale prose'};capacityFixture(n,c);
 const data=c.referenceCapacity(n);assert.equal(data.active,4);assert.equal(data.limit,50);assert.equal(data.parked,2);assert.equal(data.utilization,0.08);
 assert.deepEqual(Array.from(data.modalities,v=>[v.kind,v.active,v.limit]),[['image',2,30],['video',1,10],['audio',1,10]]);
 assert(c.capacitySummaryText(n).includes('References 4 / 50'));assert(c.capacitySummaryText(n).includes('2 Parked'));
 c.app.ui={settings:{getSettingValue:()=> 'ru'}};assert(c.capacitySummaryText(n).includes('2 отложено'));
 n.__orvCapability.__methodProfile.topology.constraint_state='UNKNOWN';assert.equal(c.referenceCapacity(n).limit,null);assert(c.capacitySummaryText(n).includes(' / ?'));
 assert.match(c.parkedReferenceTooltip(), /сохраняются.*исключаются.*восстанавливаются/);
 n.properties.orv_capability_intent.media.pop();
 assert.match(c.capacitySummaryText(n), /1 отложено/);
 n.properties.orv_capability_intent.media[0].active_name=n.inputs[0].name;
 assert.equal(c.referenceCapacity(n).parked,0);
 assert.equal(n.__orvReferenceSummary,'deliberately stale prose');
});

test('PUX05 Nodes2 meter retains one nonserialized native summary and a 3px neutral track',()=>{
 const {c,n,grid}=domFixture(),input={style:{}},children=[];capacityFixture(n,c);
 const element=()=>({style:{},children:[],textContent:'',addEventListener(){},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];}});
 c.document.createElement=element;
 n.__orvSummary={name:'REFERENCES',serialize:false,value:'legacy'};const widget=n.__orvSummary;
 const row={querySelector(s){return s==='input[aria-label="REFERENCES"]'?input:s==='.orv-capacity-summary'?children[0]:null;},append(item){children.push(item);}};
 grid.querySelectorAll=()=>[row];c.syncBetaPresentation(n);c.syncBetaPresentation(n);
 assert.equal(children.length,1);const parts=children[0].__orvParts;assert.equal(parts.count.textContent,'4 / 50');assert.equal(parts.kinds.children.length,3);assert.equal(parts.track.style.height,'3px');assert.equal(parts.fill.style.width,'8%');assert.equal(parts.track['aria-valuemax'],'50');
 assert.equal(input.style.display,'none');assert.equal(n.__orvSummary,widget);assert.equal(widget.serialize,false);
 n.__orvCapability.__methodProfile.topology.constraint_state='UNKNOWN';c.syncBetaPresentation(n);assert.equal(parts.track.role,'status');assert.equal(parts.track['aria-valuemax'],undefined);assert.equal(parts.count.textContent,'4 / ?');
});

test('renderer adapter cleans node ownership and shares one observer',()=>{
 let observers=0;const scheduled=[];const document={head:{append(){}},body:{},querySelectorAll:()=>[],createElement:()=>({})};const c=context({document,MutationObserver:class {constructor(){observers++;}observe(){}},queueMicrotask:fn=>scheduled.push(fn)});const a={},b={};c.installBetaPresentation(a);c.installBetaPresentation(a);c.installBetaPresentation(b);assert.equal(observers,1);assert.equal(c.installBetaPresentation.nodes.size,2);assert.equal(scheduled.length,1);scheduled.shift()();a.onRemoved();assert.equal(c.installBetaPresentation.nodes.size,1);b.onRemoved();assert.equal(c.installBetaPresentation.nodes.size,0);
});
test('all semantic/frontend functions and Python source exactly match immediate baseline',()=>{
 const before=execFileSync('git',['show','e89b513:web/openrouter_video.js'],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n').replace(/^import .*;\n/gm,'');const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));const a=functions(before),b=functions(reviewedRcText(new URL("../../",import.meta.url),"web/openrouter_video.js",source).replace(/^import .*;\r?\n/gm,""));for(const name of Object.keys(a))if(!['setVisible','addReadOnlyWidget','applyPresentation','syncAdvancedControls','configureGeometry','normalizedValue','configureGenerationConfiguration','restorePhase10NamedValues','bindEstimateRefresh','refreshEstimate'].includes(name))assert.equal(b[name],a[name],name);assert.equal(reviewedRcText(new URL('../../',import.meta.url),'web/openrouter_video.js',source).replace(/^import .*;\r?\n/gm,'').split('function widget')[0],before.split('function widget')[0]);
 for(const file of execFileSync('git',['ls-tree','-r','--name-only','e89b513','src'],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(file=>!['src/openrouter_video/models.py','src/openrouter_video/comfy/nodes.py','src/openrouter_video/comfy/projection.py','src/openrouter_video/comfy/routes.py','src/openrouter_video/secrets.py','src/openrouter_video/oauth.py'].includes(file)))assert.equal(reviewedRcText(root,file,readFileSync(new URL(file,root),'utf8')).replace(/\r\n/g,'\n'),execFileSync('git',['show',`e89b513:${file}`],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n'),file);
});


test('Package02 live Vue resize coalesces trusted samples and updates native bounds before release',()=>{
 const {c,n,grid}=domFixture(),root=c.document.querySelectorAll()[0],handlers={},frames=[],micro=[];let width=500,height=900,writes=0;
 root.style=geometryStyle({getPropertyValue:key=>key==='--node-width'?`${width}px`:key==='--node-height'?`${height}px`:''});root.getBoundingClientRect=()=>({width:400,height:830});root.addEventListener=(name,fn)=>handlers[name]=fn;
 c.requestAnimationFrame=fn=>{frames.push(fn);return frames.length;};c.cancelAnimationFrame=()=>{};c.queueMicrotask=fn=>micro.push(fn);
 n.size=[400,800];n.__orvMasterPromptHeight=120;n.computeSize=()=>[320,400];n.setDirtyCanvas=()=>{};n.setSize=size=>{writes++;n.size=size;n.onResize?.(size);};
 c.installResponsiveHeight(n);c.syncBetaPresentation(n);const before=n.__orvMasterPromptHeight;
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:1,target:{closest:()=>({dataset:{corner:'SE'}})}});
 for(const pair of [[500,900],[610,970],[450,910]]){[width,height]=pair;handlers.gotpointercapture({isTrusted:true,pointerId:1});handlers.pointermove({isTrusted:true,pointerId:1});micro.shift()();}
 assert.equal(frames.length,1);assert.equal(writes,0);frames.shift()();assert.equal(writes,1);assert.deepEqual(Array.from(n.size),[450,880]);assert.equal(n.__orvPreferredWidth,450);assert.equal(n.__orvMasterPromptHeight,before+80);
 assert.equal(root.style.getPropertyValue('--orv-label-width'),'144.66666666666666px');
 n.size=[999,1999];n.onResize(n.size);assert.equal(n.__orvPreferredWidth,450);assert.equal(n.__orvMasterPromptHeight,before+80);
 handlers.lostpointercapture();assert.equal(n.__orvUserResizeActive,false);assert.equal(n.size[0],450);assert.equal(n.__orvLiveSize,undefined);assert.equal(root.style.getPropertyValue('--orv-prompt-height'),`${before+80}px`);
});


test('Vue samples the same minimum as the frame and reverses without releasing capture',()=>{
 const {c,n,element}=domFixture(), handlers={}, frames=[], micro=[];
 let width=400,height=830;
 element.style=geometryStyle({getPropertyValue:key=>key==='--node-width'?`${width}px`:key==='--node-height'?`${height}px`:''});
 element.getBoundingClientRect=()=>({width:400,height:830});
 element.addEventListener=(key,fn)=>handlers[key]=fn;
 c.requestAnimationFrame=fn=>{frames.push(fn);return frames.length;};
 c.queueMicrotask=fn=>micro.push(fn);
 n.size=[400,800];n.__orvMasterPromptHeight=150;n.computeSize=()=>[320,400];
 n.setSize=size=>{n.size=size;n.onResize?.(size);};
 c.installResponsiveHeight(n);c.syncBetaPresentation(n);
 c.getComputedStyle=el=>el===element ? {minWidth:'320px'} : {};
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:1,target:{closest:()=>({dataset:{corner:'SE'}})}});
 assert.equal(element.style.minWidth,'320px');
 handlers.gotpointercapture({isTrusted:true,pointerId:1});
 for(const [wantedW,wantedH,expectedW,expectedBody,prompt] of [
  [280,810,320,780,130], [230,660,320,692,42],
  [150,490,320,692,42], [355,752,355,722,72],
 ]){
  width=Math.max(parseFloat(element.style.minWidth),wantedW);
  height=Math.max(722,wantedH);
  handlers.pointermove({isTrusted:true,pointerId:1});micro.shift()();frames.shift()();
  assert.equal(n.__orvUserResizeActive,true);
  assert.deepEqual(Array.from(n.size),[expectedW,expectedBody]);
  assert.equal(n.__orvMasterPromptHeight,prompt);
 }
 handlers.lostpointercapture();
 assert.equal(element.style.minWidth,'');
});

test('Vue native window drag is observed after its write, not the root capture microtask',()=>{
 const {c,n}=domFixture(),root=c.document.querySelectorAll()[0],handlers={},windowHandlers={},micro=[],frames=[];
 let width=400,height=830;
 const win={addEventListener:(name,fn)=>windowHandlers[name]=fn,removeEventListener:name=>delete windowHandlers[name]};
 root.ownerDocument={defaultView:win};
 root.style=geometryStyle({getPropertyValue:key=>key==='--node-width'?`${width}px`:key==='--node-height'?`${height}px`:''});
 root.getBoundingClientRect=()=>({width:400,height:830});
 root.addEventListener=(name,fn)=>handlers[name]=fn;root.removeEventListener=name=>delete handlers[name];
 c.queueMicrotask=fn=>micro.push(fn);c.requestAnimationFrame=fn=>{frames.push(fn);return frames.length;};c.cancelAnimationFrame=()=>{};
 n.size=[400,800];n.__orvMasterPromptHeight=120;n.computeSize=()=>[320,400];n.setSize=size=>{n.size=size;n.onResize?.(size);};n.setDirtyCanvas=()=>{};
 c.installResponsiveHeight(n);c.syncBetaPresentation(n);const before=n.__orvMasterPromptHeight;
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:3,target:{closest:()=>({dataset:{corner:'SE'}})}});
 handlers.gotpointercapture?.({isTrusted:true,pointerId:3});
 const e={isTrusted:true,pointerId:3};handlers.pointermove?.(e);while(micro.length)micro.shift()();
 // Installed native useNodeResize writes at window bubble, after root listeners.
 width=620;height=1030;windowHandlers.pointermove?.(e);while(micro.length)micro.shift()();
 assert.equal(n.__orvPreferredWidth,620);assert.equal(n.__orvMasterPromptHeight,before+200);
 const saved=n.__orvMasterPromptHeight;width=999;height=1999;n.onResize([999,1999]);assert.equal(n.__orvMasterPromptHeight,saved);
 handlers.lostpointercapture();assert.equal(windowHandlers.pointermove,undefined);assert.equal(n.__orvUserResizeActive,false);
});


test('Vue pointerdown preserves the native starting rectangle until capture',()=>{
 const {c,n,grid}=domFixture(),root=c.document.querySelectorAll()[0],handlers={};
 root.style={};root.getBoundingClientRect=()=>({width:400,height:grid.style.flex==='1 1 auto'?600:830});
 root.addEventListener=(name,fn)=>handlers[name]=fn;root.removeEventListener=()=>{};
 n.size=[400,800];n.__orvMasterPromptHeight=120;n.computeSize=()=>[320,400];c.installResponsiveHeight(n);c.syncBetaPresentation(n);
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:1,target:{closest:()=>({dataset:{corner:'SE'}})}});
 // Native startResize records getBoundingClientRect after root capture.
 assert.equal(root.getBoundingClientRect().height,830);
 handlers.gotpointercapture({isTrusted:true,pointerId:1});assert.equal(grid.style.flex,undefined);
});

test('Nodes 2.0 shrinking exposes Prompt minimum only after native capture and commits vertical reduction',()=>{
 const {c,n,element}=domFixture(),handlers={},frames=[],micro=[];
 element.style=geometryStyle({getPropertyValue:key=>key==='--node-width'?'400px':key==='--node-height'?'755px':''});
 element.getBoundingClientRect=()=>({width:400,height:830});
 element.addEventListener=(key,fn)=>handlers[key]=fn;
 c.requestAnimationFrame=fn=>frames.push(fn);c.queueMicrotask=fn=>micro.push(fn);
 n.size=[400,800];n.__orvMasterPromptHeight=150;n.computeSize=()=>[320,400];
 c.installResponsiveHeight(n);c.syncBetaPresentation(n);
 handlers.pointerdown({isTrusted:true,button:0,clientX:0,clientY:0,pointerId:1,target:{closest:()=>({dataset:{corner:'SE'}})}});
 assert.equal(element.getAttribute('data-orv-resizing'),undefined);
 handlers.gotpointercapture({isTrusted:true,pointerId:1});
 assert.equal(element.getAttribute('data-orv-resizing'),'');
 assert.equal(element.style.getPropertyValue('--orv-prompt-minimum'),'42px');
 assert.match(source,/\[data-orv-resizing\][^}]*var\(--node-height/);
 handlers.pointermove({isTrusted:true,pointerId:1});micro.shift()();
 assert.equal(n.__orvMasterPromptHeight,75);
 handlers.lostpointercapture();
 assert.equal(element.getAttribute('data-orv-resizing'),undefined);
 assert.equal(element.style.getPropertyValue('--orv-prompt-height'),'75px');
});
