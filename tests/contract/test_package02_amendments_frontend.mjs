import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';import vm from 'node:vm';import test from 'node:test';
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const models=JSON.parse(readFileSync(new URL('../fixtures/package02-provider-projection.json',import.meta.url),'utf8')).models;
const avatar=models.find(m=>m.model_id==='heygen/avatar-iv');
const plain=x=>JSON.parse(JSON.stringify(x));
function harness(locale='en'){
 const c={app:{registerExtension(){},ui:{settings:{getSettingValue:k=>k==='Comfy.Locale'?locale:false}}},api:{},document:{querySelectorAll:()=>[]}};
 c.ComfyWidgets={STRING(n,name,info){const w=n.addWidget('customtext',name,info[1].default,null,{multiline:true});w.element={style:{}};return {widget:w};}};
 vm.runInNewContext(source,c);c.publishSemanticProjection=()=>{};c.refreshEstimate=async()=>{};
 const n={size:[500,800],pos:[51,73],id:8,properties:{},inputs:[],__orvProjectedKey:'heygen/avatar-iv|IR2V',widgets:[{name:'prompt',label:'prompt',value:'speech',options:{},element:{style:{}}},{name:'provider_options',value:'[]',options:{}}],addWidget(type,name,value,callback,options={}){const w={type,name,value,callback,options};this.widgets.push(w);return w;},computeSize(){return [400,200+this.widgets.filter(w=>!w.hidden).reduce((sum,w)=>sum+(w.computeSize?.()[1]||20)+4,0)];},setSize(size){this.size=Float32Array.from(size);this.onResize?.(this.size);},setDirtyCanvas(){}};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);
 return {c,n};
}
const get=(n,key)=>n.widgets.find(w=>w.name===`provider_option:heygen::${key}`);
const saved=n=>JSON.parse(n.widgets.find(w=>w.name==='provider_options').value);
function project(c,n,method='IR2V') {const p=avatar.method_profiles[method];n.__orvCapability={__methodProfile:p};n.widgets[0].hidden=p.controls.prompt.state!=='SUPPORTED';const issue=c.configureOperationControls(n,p);c.fitPresentationWidth(n);return issue;}

for(const locale of ['en','ru'])test(`real Avatar semantic controls and actionable required Voice ID ${locale}`,()=>{
 const {c,n}=harness(locale);const issue=project(c,n);assert.match(issue,locale==='ru'?/ID голоса/:/Voice ID/);
 const motion=get(n,'motion_prompt');assert.equal(motion.type,'customtext');assert.equal(motion.label,'motion prompt');assert.equal(motion.options.multiline,true);assert.equal(motion.element.style.padding,'4px 6px');assert.equal(motion.computeSize()[1],n.widgets[0].computeSize()[1]);
 assert(!n.widgets.some(w=>w.name.endsWith(':override')));
 assert.equal(get(n,'voice_settings:speed').type,'slider');assert.equal(get(n,'voice_settings:speed').value,1);assert.equal(get(n,'voice_settings:speed').__orvProviderAuto,true);
 assert.equal(get(n,'voice_settings:pitch').value,0);assert.equal(get(n,'voice_settings:volume').value,1);
 assert.equal(get(n,'remove_background').type,'combo');assert.equal(get(n,'title').type,'text');assert.equal(get(n,'caption:style').type,'combo');assert(!get(n,'caption:style').hidden);
 assert.equal(saved(n).length,0);get(n,'voice_id').callback('voice-native');assert.equal(project(c,n),'');
 assert(n.widgets.some(w=>w.__orvProviderHeading && !w.hidden));
});

test('numeric direct edit/manual/reset and boolean Auto/On/Off preserve explicit zero and false',()=>{
 const {c,n}=harness();project(c,n);const pitch=get(n,'voice_settings:pitch'),flag=get(n,'remove_background');
 pitch.callback(0);assert.equal(saved(n).find(v=>v.path?.[0]==='pitch').value,0);assert.equal(pitch.__orvProviderAuto,false);
 flag.callback(false);assert.equal(saved(n).find(v=>v.key==='remove_background').value,false);flag.callback(true);assert.equal(saved(n).find(v=>v.key==='remove_background').value,true);
 flag.__orvResetProvider();pitch.__orvResetProvider();assert.equal(saved(n).length,0);assert.equal(pitch.__orvProviderAuto,true);
 const menu=[];n.getExtraMenuOptions(null,menu);assert(menu[0].submenu.options.some(v=>v.content.includes('Voice Pitch')));
});

test('unknown numeric Auto has no fabricated default or slider position',()=>{
 const {c,n}=harness();c.configureOperationControls(n,{controls:{provider_options:{state:'SUPPORTED',providers:{test:{strength:{type:'number',min:0,max:1}}}}}});
 let w=n.widgets.find(w=>w.name==='provider_option:test::strength');assert.equal(w.type,'number');assert.equal(w.value,null);assert.equal(c.providerDisplayValue(w),'Auto');assert.equal(saved(n).length,0);
 w.callback(0);w=n.widgets.find(w=>w.name==='provider_option:test::strength');assert.equal(w.type,'slider');assert.equal(w.value,0);assert.equal(saved(n)[0].value,0);
 w.__orvResetProvider();w=n.widgets.find(w=>w.name==='provider_option:test::strength');assert.equal(w.type,'number');assert.equal(w.value,null);assert.equal(saved(n).length,0);
});

test('Background context variants omit inactive values and recover exact prior intent',()=>{
 const {c,n}=harness();project(c,n);get(n,'background:type').callback('color');assert(!get(n,'background:value').hidden);assert(!get(n,'background:url') || get(n,'background:url').hidden);
 get(n,'background:value').callback('#123456');get(n,'background:type').callback('image');assert(get(n,'background:value').hidden);assert(!saved(n).some(v=>v.path?.[0]==='value'));
 get(n,'background:url').callback('https://example.test/bg.png');get(n,'background:asset_id').callback('asset1');assert(!saved(n).some(v=>v.path?.[0]==='url'));assert(saved(n).some(v=>v.path?.[0]==='asset_id'));
 get(n,'background:type').callback('color');assert.equal(get(n,'background:value').value,'#123456');assert(!saved(n).some(v=>v.path?.[0]==='asset_id'));
 get(n,'background:type').__orvResetProvider();assert(!saved(n).some(v=>v.key==='background'));get(n,'background:type').callback('image');assert.equal(get(n,'background:asset_id').value,'asset1');
 assert(JSON.stringify(n.properties).includes('https://example.test/bg.png'));
});

test('Voice engine variants park incompatible options and restore valid branch intent',()=>{
 const {c,n}=harness();project(c,n);const prefix='voice_settings:engine_settings:';
 get(n,prefix+'engine_type').callback('elevenlabs');get(n,prefix+'model').callback('eleven_v4');get(n,prefix+'style').callback(0);get(n,prefix+'use_speaker_boost').callback(false);
 get(n,prefix+'engine_type').callback('fish');assert(!saved(n).some(v=>['style','use_speaker_boost'].includes(v.path?.at(-1))));assert.equal(get(n,prefix+'model').value,'Auto');get(n,prefix+'model').callback('s2.1-pro');
 get(n,prefix+'engine_type').callback('starfish');assert(get(n,prefix+'model').hidden);assert(!saved(n).some(v=>v.path?.at(-1)==='model'));
 get(n,prefix+'engine_type').callback('elevenlabs');assert.equal(get(n,prefix+'model').value,'eleven_v4');assert.equal(saved(n).find(v=>v.path?.at(-1)==='style').value,0);assert.equal(saved(n).find(v=>v.path?.at(-1)==='use_speaker_boost').value,false);
 get(n,prefix+'engine_type').__orvResetProvider();assert(!saved(n).some(v=>v.path?.includes('engine_settings')));
});

test('master geometry adds H+gap per field and preserves width/anchor through 1→2→3→1',()=>{
 const {c,n}=harness();c.configureOperationControls(n,{controls:{}});c.persistMasterPromptHeight(n,180);c.fitPresentationWidth(n);const height=n.size[1],width=n.size[0];
 const add=count=>{const fields={};for(let i=0;i<count;i++)fields['field'+i]={type:'string',text_semantic:'creative_prompt'};c.configureOperationControls(n,{controls:{provider_options:{state:'SUPPORTED',providers:{test:fields}}}});c.fitPresentationWidth(n);};
 add(1);assert.equal(c.textRegionGeometry(n).field,180);const two=n.size[1];assert(two>=height+184);
 add(2);assert.equal(c.textRegionGeometry(n).budget,548);assert.equal(n.size[1]-two,184);assert(c.creativeTextWidgets(n).every(w=>w.computeSize()[1]===180));
 add(0);assert.equal(c.textRegionGeometry(n).field,180);assert.equal(n.size[0],width);assert.deepEqual(n.pos,[51,73]);assert.equal(n.properties.orv_prompt_geometry.height,180);
});

test('multi-field trusted native resize derives and persists per-field master height',()=>{
 const {c,n}=harness();project(c,n);c.persistMasterPromptHeight(n,180);c.fitPresentationWidth(n);const min=n.computeSize()[1],region=c.textRegionGeometry(n);
 n.__orvCommitResizeIntent(620,min+2*(224-58));assert.equal(n.__orvMasterPromptHeight,224);assert.equal(n.properties.orv_prompt_geometry.height,224);
 for(const size of [[999,3000],[320,100]]){n.size=size;n.onResize(n.size);assert.equal(n.__orvMasterPromptHeight,224);}
 assert.equal(c.textRegionGeometry(n).field,224);assert.equal(region.count,2);
});

test('audio-driven method retains master for supported motion without exposing script or TTS controls',()=>{
 const {c,n}=harness();project(c,n);c.persistMasterPromptHeight(n,224);get(n,'motion_prompt').callback('head motion\nsmile');
 project(c,n,'AVATAR_AUDIO');assert(n.widgets[0].hidden);assert.equal(c.creativeTextWidgets(n).length,1);assert.equal(get(n,'motion_prompt').computeSize()[1],224);assert.equal(get(n,'motion_prompt').value,'head motion\nsmile');assert(get(n,'voice_id').hidden);
 project(c,n,'IR2V');assert(!n.widgets[0].hidden);assert.equal(c.textRegionGeometry(n).budget,452);
});

test('save/restore/duplicate retain master and reversible variant values per instance',()=>{
 const {c,n}=harness();project(c,n);c.persistMasterPromptHeight(n,211);get(n,'background:type').callback('color');get(n,'background:value').callback('#ABCDEF');get(n,'background:type').callback('image');
 const data=plain({properties:n.properties,provider_options:n.widgets[1].value,size:Array.from(n.size)});
 const b=harness();b.n.properties=plain(data.properties);delete b.n.__orvMasterPromptHeight;b.n.widgets[1].value=data.provider_options;b.n.__orvRestoreGeometry=data.size;project(b.c,b.n);
 assert.equal(b.n.__orvMasterPromptHeight,211);get(b.n,'background:type').callback('color');assert.equal(get(b.n,'background:value').value,'#ABCDEF');b.c.persistMasterPromptHeight(b.n,300);assert.equal(n.properties.orv_prompt_geometry.height,211);
});

for(const locale of ['en','ru','zh','ja','ko','ar','he','hi','fr','de','es','pt-BR','tr'])test(`node-scoped native typography tokens stay identical in ${locale}`,()=>{
 const {c,n}=harness(locale);n.innerFontStyle='normal 12px Inter';project(c,n);const token=c.nodeTypography(n);assert.equal(token.size,12);assert.equal(token.weight,400);assert(token.family.endsWith('sans-serif'));assert(!token.family.match(/(?:^|,\s*)serif(?:,|$)/));
 const calls=[],stack=[],ctx={font:'24px serif',textBaseline:'middle',save(){stack.push([this.font,this.textBaseline]);},restore(){[this.font,this.textBaseline]=stack.pop();}};
 const item={name:'other',draw(ctx){calls.push([ctx.font,ctx.textBaseline]);}};n.widgets.push(item);c.installNodeTypography(n);item.draw(ctx);assert.equal(calls[0][0],`400 12px ${token.family}`);assert.equal(calls[0][1],'alphabetic');assert.equal(ctx.font,'24px serif');assert.equal(ctx.textBaseline,'middle');
 assert.equal(get(n,'motion_prompt').element.style.fontFamily,token.family);assert.equal(get(n,'motion_prompt').element.style.lineHeight,'18px');
});

test('Wan audio is a short URL field, never classified from its key as a creative prompt',()=>{
 const {c,n}=harness();const wan=models.find(m=>m.model_id==='alibaba/wan-2.6');for(const method of ['T2V','I2V']){c.configureOperationControls(n,wan.method_profiles[method]);const w=n.widgets.find(w=>w.name==='provider_option:atlas-cloud::audio');assert.equal(w.type,'text');assert.equal(w.label,'Audio URL');assert(!w.__orvTextSemantic);w.callback('https://example.test/audio.mp3');assert.equal(saved(n).find(v=>v.key==='audio').value,'https://example.test/audio.mp3');}
});


test('native save names fixed values independently of added nonserialized controls and preserves previous hooks',()=>{
 const {c,n}=harness();n.widgets.push({name:'model',value:'heygen/avatar-iv'},{name:'inference_method',value:'IR2V'},{name:'geometry_authority',value:'NORMALIZED'},{name:'randomize',label:'control after generate',value:'fixed'},{name:'creativity',value:0});
 let previous=0;n.onSerialize=data=>{previous++;if(data)data.other='preserved';};c.installSemanticSerialization(n);c.installSemanticSerialization(n);project(c,n);get(n,'voice_id').callback('voice');
 const data={widgets_values:n.widgets.map(w=>w.serialize===false?null:w.value),widgets_values_named:{external:'keep'}};n.onSerialize(data);
 assert.equal(previous,1);assert.equal(data.other,'preserved');assert.equal(data.widgets_values_named.external,'keep');assert.equal(data.widgets_values_named.geometry_authority,'NORMALIZED');assert.equal(data.widgets_values_named.creativity,0);assert.equal(data.widgets_values_named.randomize,'fixed');assert.equal(data.widgets_values_named.provider_options,n.widgets.find(w=>w.name==='provider_options').value);
 const b=harness();b.n.widgets.push(...n.widgets.filter(w=>['model','inference_method','geometry_authority','randomize','creativity'].includes(w.name)).map(w=>({...w,value:null})));
 assert.equal(b.c.restorePhase10NamedValues(b.n,data.widgets_values_named),true);assert.equal(b.n.widgets.find(w=>w.name==='geometry_authority').value,'NORMALIZED');assert.equal(b.n.widgets.find(w=>w.name==='randomize').value,'fixed');assert.doesNotThrow(()=>n.onSerialize());
});

test('Nodes2 numeric state uses one compact accessible reset and never edits the native binding',()=>{
 const {c,n}=harness();project(c,n);const item=get(n,'voice_settings:speed'),children=[];const host={append(x){children.push(x);},querySelector:()=>children[0]};
 const input={parentElement:host,getAttribute:()=>item.name,style:{}},label={textContent:item.label};const row={querySelector:s=>s==='input'?input:s.includes('widget-layout-field-label')?label:null};
 let writes=0,text='';c.document.createElement=()=>({style:{},get textContent(){return text;},set textContent(value){writes++;text=value;},setAttribute(k,v){this[k]=v;},addEventListener(name,fn){this[name]=fn;}});
 c.syncProviderNumericState(n,row);c.syncProviderNumericState(n,row);assert.equal(writes,1,'unchanged text must not trigger the native subtree observer again');assert.equal(children.length,1);assert.equal(children[0].textContent,'Auto');assert.equal(item.value,1);assert.equal(saved(n).length,0);
 item.callback(1.2);c.syncProviderNumericState(n,row);assert.equal(children[0].textContent,'↺');children[0].click({stopPropagation(){}});assert.equal(saved(n).length,0);assert.equal(item.__orvProviderAuto,true);
});


test('capacity DOM reaches a stable text projection without rescheduling the subtree observer',()=>{
 const {c,n}=harness(),nodes=[],children=[];
 c.document.createElement=()=>{let text='';const e={style:{},children:[],writes:0,get textContent(){return text;},set textContent(value){this.writes++;text=value;},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];}};nodes.push(e);return e;};
 n.__orvCapability={__methodProfile:{topology:{reference_kinds:['image'],max:3,per_kind_max:{image:3}}}};
 const row={querySelector:()=>children[0],append:e=>children.push(e)},input={style:{}};
 c.syncCapacityMeter(n,row,input);const writes=nodes.reduce((sum,n)=>sum+n.writes,0);c.syncCapacityMeter(n,row,input);
 assert.equal(nodes.reduce((sum,n)=>sum+n.writes,0),writes,'unchanged capacity text must not feed the native MutationObserver');
});


test('native Canvas body and title getters retain hierarchy with explicit sans fallbacks only on this node',()=>{
 const {c,n}=harness(),other={innerFontStyle:'normal 12px Inter',titleFontStyle:'14px Inter'};
 n.innerFontStyle='normal 12px Inter';n.titleFontStyle='14px Inter';c.installNodeTypography(n);
 assert.equal(n.innerFontStyle,`normal 12px ${c.nodeTypography(n).family}`);assert.equal(n.titleFontStyle,`14px ${c.nodeTypography(n).family}`);assert.equal(other.innerFontStyle,'normal 12px Inter');assert.equal(other.titleFontStyle,'14px Inter');
 const before=n.innerFontStyle;c.installNodeTypography(n);assert.equal(n.innerFontStyle,before);
});


test('native drawWidget path receives scoped sans typography and restores inherited Canvas state',()=>{
 const {c}=harness('ru');let observed;
 const w={name:'native_slider',drawWidget(ctx){observed=ctx.font;},options:{}};
 const n={widgets:[w],innerFontStyle:'normal 12px Inter',titleFontStyle:'14px Inter'};
 const ctx={font:'10px serif',textBaseline:'top',save(){this.saved=[this.font,this.textBaseline];},restore(){[this.font,this.textBaseline]=this.saved;}};
 c.installNodeTypography(n);const draw=w.drawWidget;c.installNodeTypography(n);assert.equal(w.drawWidget,draw);
 w.drawWidget(ctx,{});assert.match(observed,/12px .*sans-serif/);assert.equal(ctx.font,'10px serif');assert.equal(ctx.textBaseline,'top');
});
