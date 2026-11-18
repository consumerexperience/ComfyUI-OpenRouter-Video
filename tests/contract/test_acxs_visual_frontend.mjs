import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const plain=x=>JSON.parse(JSON.stringify(x));
function context(locale='en') {
 const c={app:{registerExtension(){},ui:{settings:{getSettingValue:k=>k==='Comfy.Locale'?locale:false}}},api:{},document:{querySelectorAll:()=>[]}};
 c.ComfyWidgets={STRING(n,name,info){const w=n.addWidget('customtext',name,info[1].default,null,{multiline:true});w.element={style:{}};return {widget:w};}};
 vm.runInNewContext(source,c);return c;
}
function node(c) {
 const n={size:[400,800],pos:[10,20],inputs:[],widgets:[{name:'prompt',label:'prompt',value:'primary\ntext',options:{}},{name:'provider_options',value:'[]',options:{}}],
  addWidget(type,name,value,callback,options={}){const w={type,name,value,callback,options};this.widgets.push(w);return w;},
  computeSize(){return [400,200+this.widgets.filter(w=>!w.hidden).reduce((s,w)=>s+(w.computeSize?.()[1]||20)+4,0)];},
  setSize(size){this.size=Float32Array.from(size);this.onResize?.(this.size);},setDirtyCanvas(){}};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);return n;
}
function profile(spec) {return {controls:{provider_options:{state:'SUPPORTED',providers:{test:spec}}}};}
function project(c,n,p) {n.__orvCapability={__methodProfile:p};return c.configureOperationControls(n,p);}

test('Master height gives identical additive full-width creative fields, not ordinary technical inputs',()=>{
 const c=context(),n=node(c);n.__orvMasterPromptHeight=304;
 const p=profile({negative:{type:'string',text_semantic:'negative_prompt'},title:{type:'string'}});
 project(c,n,p);const fields=c.creativeTextWidgets(n);assert.equal(fields.length,2);
 assert.deepEqual(Array.from(fields,w=>w.label),['prompt','negative prompt']);
 assert.equal(fields[1].type,'customtext');assert.equal(fields[1].options.multiline,true);assert.equal(fields[1].serialize,false);
 assert.equal(n.widgets.find(w=>w.name.endsWith(':title')).type,'text');
 assert.equal(fields[0].computeSize()[1],304);assert.equal(fields[1].computeSize()[1],304);
 assert.equal(fields[0].element?.placeholder,undefined);assert.equal(fields[1].element.placeholder,'negative prompt');
 assert.equal(n.widgets.indexOf(fields[1]),n.widgets.indexOf(fields[0])+1);
});

test('creative presentation is evidence-driven, never inferred from negativePrompt spelling',()=>{
 const c=context(),n=node(c);project(c,n,profile({negativePrompt:{type:'string'},arbitrary:{type:'string',text_semantic:'negative_prompt'}}));
 assert.equal(n.widgets.find(w=>w.name.endsWith(':negativePrompt')).type,'text');
 assert.equal(n.widgets.find(w=>w.name.endsWith(':arbitrary')).type,'customtext');
});

test('Additive allocation preserves master height through temporary minima, visibility and ordinary rows',()=>{
 const c=context(),n=node(c);n.__orvMasterPromptHeight=100;const one=c.textRegionGeometry(n);
 project(c,n,profile({a:{type:'string',text_semantic:'negative_prompt'},b:{type:'string',text_semantic:'creative_prompt'}}));
 assert.equal(c.textRegionGeometry(n).budget,308);assert.equal(c.textRegionGeometry(n).field,100);assert.equal(n.__orvMasterPromptHeight,100);
 project(c,n,profile({technical:{type:'string'}}));assert.equal(c.textRegionGeometry(n).budget,one.budget);assert.equal(n.__orvMasterPromptHeight,100);
 n.__orvMasterPromptHeight=604;project(c,n,profile({a:{type:'string',text_semantic:'negative_prompt'},b:{type:'string',text_semantic:'creative_prompt'}}));
 assert.equal(c.textRegionGeometry(n).field,604);assert.deepEqual(n.pos,[10,20]);
});

test('user resize budget is independent from programmatic, deferred and restored callbacks',()=>{
 const c=context(),a=node(c),b=node(c);a.__orvCommitResizeIntent(620,a.computeSize()[1]+300);
 const budget=a.__orvMasterPromptHeight;assert.equal(budget,c.textRegionGeometry(a).min+300);
 for(const total of [10,4000,500]){a.size=[1000,total];a.onResize(a.size);assert.equal(a.__orvPreferredWidth,620);assert.equal(a.__orvMasterPromptHeight,budget);}
 project(c,a,profile({a:{type:'string',text_semantic:'negative_prompt'}}));c.fitPresentationWidth(a);
 assert.equal(a.size[0],620);assert.equal(a.__orvMasterPromptHeight,budget);assert.notEqual(a.__orvMasterPromptHeight,b.__orvMasterPromptHeight);
});

test('native creative widget callbacks preserve newline text and optional boolean omission',()=>{
 const c=context(),n=node(c);c.publishSemanticProjection=()=>{};c.refreshEstimate=async()=>{};
 const p=profile({negative:{type:'string',text_semantic:'negative_prompt'},flag:{type:'boolean'}});project(c,n,p);
 const negative=n.widgets.find(w=>w.__orvTextSemantic),flag=n.widgets.find(w=>w.name.endsWith(':flag'));
 assert.equal(flag.type,'combo');assert(!flag.hidden);assert.equal(n.widgets.find(w=>w.name==='provider_options').value,'[]');
 negative.callback('one\ntwo');flag.callback(true);
 let saved=JSON.parse(n.widgets.find(w=>w.name==='provider_options').value);assert.equal(saved.find(v=>v.key==='negative').value,'one\ntwo');assert.equal(saved.find(v=>v.key==='flag').value,true);
 flag.__orvResetProvider();saved=JSON.parse(n.widgets.find(w=>w.name==='provider_options').value);assert(!saved.some(v=>v.key==='flag'));
 project(c,n,{controls:{}});assert(negative.hidden);assert(saved.some(v=>v.value==='one\ntwo'));project(c,n,p);assert.equal(negative.value,'one\ntwo');
});

test('dynamic numeric ranges and enums reuse their semantic native components',()=>{
 const c=context(),n=node(c);project(c,n,profile({range:{type:'number',min:0,max:1,omitted_default:0.5},discrete:{type:'integer',values:[1,4,9]},short:{type:'string'}}));
 assert.equal(n.widgets.find(w=>w.name.endsWith(':range')).type,'slider');assert.equal(n.widgets.find(w=>w.name.endsWith(':discrete')).type,'combo');assert.equal(n.widgets.find(w=>w.name.endsWith(':short')).type,'text');
});

test('a changing dynamic domain replaces the native component without duplicating widget identity or links',()=>{
 const c=context(),n=node(c);const widgets=n.widgets;n.inputs=[{name:'provider_option:test::mode',link:17}];
 project(c,n,profile({mode:{type:'integer',values:[1,4,9]}}));assert.equal(n.widgets.find(w=>w.name==='provider_option:test::mode').type,'combo');
 project(c,n,profile({mode:{type:'integer',min:1,max:9}}));assert.equal(n.widgets.find(w=>w.name==='provider_option:test::mode').type,'number');
 c.publishSemanticProjection=()=>{};c.refreshEstimate=async()=>{};n.widgets.find(w=>w.name==='provider_option:test::mode').callback(4);assert.equal(n.widgets.find(w=>w.name==='provider_option:test::mode').type,'slider');
 assert.equal(n.widgets,widgets);assert.equal(n.widgets.filter(w=>w.name==='provider_option:test::mode').length,1);assert.equal(n.inputs[0].link,17);
});

test('unsupported linked creative text is diagnosed without deleting connection or saved value',()=>{
 const c=context(),n=node(c),p=profile({negative:{type:'string',text_semantic:'negative_prompt'}});project(c,n,p);
 n.inputs=[{name:'provider_option:test::negative',link:99,widget:{name:'provider_option:test::negative'}}];
 assert.match(project(c,n,{controls:{}}),/connection is preserved/);assert.equal(n.inputs[0].link,99);
 assert.equal(c.projectProviderCostControls(n,[]).state,'INVALID');project(c,n,p);assert.equal(n.__orvLinkedCreativeIssue,false);
});

for(const locale of ['en','ru']) test(`Read-only Duration has separate localized label/value/state with numeric wire (${locale})`,()=>{
 const c=context(locale),item={name:'duration',value:8,__orvDurationAdapter:true,__orvDurationPresentation:'FIXED'};
 const parts=c.readOnlyValueParts(item);assert.equal(item.value,8);assert.equal(c.durationPresentationLabel(item),locale==='ru'?'Длительность':'Duration');assert.equal(parts.value,locale==='ru'?'8 с':'8 s');assert.equal(parts.state,locale==='ru'?'Фиксировано':'Fixed');
 item.value=-1;item.__orvDurationPresentation='AUTOMATIC';assert.equal(c.readOnlyValueParts(item).value,locale==='ru'?'Авто':'Auto');assert.equal(item.value,-1);
});

test('actual Vue Prompt DOM with empty placeholder and native associated label is recognized',()=>{
 const c=context(),n=node(c),area={placeholder:'',rows:5,style:{},getAttribute:()=>null,setAttribute(k,v){this[k]=v;}},label={textContent:'prompt',style:{}},marks=[];
 const row={style:{},querySelector:s=>s==='textarea'?area:s==='label[for]'?label:null,classList:{add:x=>marks.push(x),remove(){}}};
 const grid={style:{},querySelectorAll:()=>[row]},header={querySelector:()=>null,append(){}},root={dataset:{nodeId:'1'},classList:{add(){}},querySelector:s=>s.startsWith('.lg-node-header')?null:grid};
 c.document={querySelectorAll:()=>[root]};n.id=1;n.__orvMasterPromptHeight=224;c.syncBetaPresentation(n);
 assert(marks.includes('orv-prompt-row'));assert.equal(grid.style.gridTemplateRows,'224px');assert.equal(area.placeholder,'prompt');assert.equal(label.style.display,'none');assert.equal(area['aria-label'],'prompt');
});

test('intrinsic native flow excludes blank flex slack and counts structural spacing exactly once',()=>{
 const c=context();c.getComputedStyle=e=>e.css;
 const leaf=h=>({css:{display:'block',position:'static'},getBoundingClientRect:()=>({height:h*2})});
 const column=(children,padding=0,gap=0)=>({children,css:{display:'flex',flexDirection:'column',position:'static',rowGap:String(gap),paddingTop:String(padding),paddingBottom:String(padding)},getBoundingClientRect:()=>({height:4000})});
 const body=column([leaf(100),leaf(224),leaf(24)],4,4),root=column([leaf(40),body]);
 assert.equal(c.nativeFlowHeight(root,2),40+100+224+24+8+8);
});

test('unknown duration never masquerades as a fixed or automatic value',()=>{
 const c=context(),item={value:0,__orvDurationAdapter:true,__orvDurationPresentation:'UNKNOWN'};
 assert.equal(c.readOnlyValueParts(item).value,'—');assert.notEqual(c.readOnlyValueParts(item).state,'Fixed');assert.equal(item.value,0);
});

test('horizontal-only Classic gesture cannot promote a temporary N-field minimum to user budget',()=>{
 const c=context(),handlers={};let n;c.app.canvas={canvas:{addEventListener:(key,fn)=>handlers[key]=fn},graph:{getNodeById:()=>n}};const microtasks=[];c.queueMicrotask=fn=>microtasks.push(fn);
 n=node(c);n.id=1;n.findResizeDirection=()=> 'SE';n.__orvMasterPromptHeight=70;
 project(c,n,profile({negative:{type:'string',text_semantic:'negative_prompt'}}));c.fitPresentationWidth(n);const originalHeight=n.size[1];
 c.app.canvas.pointer={onDrag:()=>n.onResize(n.size)};handlers.pointerdown({isTrusted:true,button:0,canvasX:0,canvasY:0,pointerId:1});
 const e={isTrusted:true,pointerId:1};handlers.pointermove(e);c.app.canvas.pointer.eMove=e;n.size=[620,originalHeight];c.app.canvas.pointer.onDrag(e);
 assert.equal(n.__orvMasterPromptHeight,70);assert.equal(n.__orvPreferredWidth,620);
 project(c,n,{controls:{}});assert.equal(c.textRegionGeometry(n).budget,70);while(microtasks.length)microtasks.shift()();
});

test('native multiline minima retain independent master height and release additive allocation on hide',()=>{
 const c=context(),n=node(c);project(c,n,profile({neg:{type:'string',text_semantic:'negative_prompt'}}));n.__orvMasterPromptHeight=224;n.id=1;
 const areas=[{placeholder:'',rows:4},{placeholder:'',rows:4}];const rows=areas.map((area,i)=>({style:{},classList:{add(){},remove(){}},querySelector:s=>s==='textarea'?area:s==='label[for]'?{textContent:i?'negative prompt':'prompt',style:{}}:null}));
 const grid={style:{},querySelectorAll:()=>rows};const root={dataset:{nodeId:'1'},classList:{add(){}},querySelector:s=>s.startsWith('.lg-node-header')?null:grid};c.document={querySelectorAll:()=>[root]};c.getComputedStyle=()=>({minHeight:'64px'});
 c.syncBetaPresentation(n);assert.equal(grid.style.gridTemplateRows,'224px 224px');assert.equal(areas[0].placeholder,'prompt');assert.equal(areas[1].placeholder,'negative prompt');
 n.__orvMasterPromptHeight=70;c.syncBetaPresentation(n);assert.equal(grid.style.gridTemplateRows,'70px 70px');assert.equal(n.__orvMasterPromptHeight,70);
 n.widgets.find(w=>w.__orvTextSemantic).hidden=true;rows.pop();c.syncBetaPresentation(n);assert.equal(grid.style.gridTemplateRows,'70px');assert.equal(n.__orvMasterPromptHeight,70);
});

test('read-only native Duration replaces only its value cell and restores native editing without duplicates',()=>{
 const c=context(),n=node(c),duration={name:'duration',value:8,__orvDurationAdapter:true,__orvDurationPresentation:'FIXED',options:{read_only:true}};n.widgets.push(duration);
 const make=()=>({style:{},children:[],setAttribute(k,v){this[k]=v;},append(...values){this.children.push(...values);},remove(){this.removed=true;}});
 c.document={createElement:make};const input={getAttribute:()=> 'duration'},cell={style:{display:'inline-flex'},contains:e=>e===input};
 const row={children:[cell],querySelector:s=>s==='input'?input:s==='.orv-duration-readonly'?row.children.find(e=>e.className==='orv-duration-readonly'&&!e.removed):null,append:e=>row.children.push(e)};
 c.syncReadOnlyDurationRow(n,{},row);c.syncReadOnlyDurationRow(n,{},row);const display=row.children[1];assert.equal(row.children.length,2);assert.equal(cell.style.display,'none');assert.equal(display.children[0].textContent,'8 s');assert.equal(display.children[1].textContent,'Fixed');assert.equal(display.role,'status');assert.equal(display.style.opacity,undefined);
 duration.options.read_only=false;c.syncReadOnlyDurationRow(n,{},row);assert.equal(cell.style.display,'inline-flex');assert(display.removed);assert.equal(duration.value,8);
});
