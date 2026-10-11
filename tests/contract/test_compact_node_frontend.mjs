import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import test from 'node:test';
const root=new URL('../../',import.meta.url);
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const context={app:{registerExtension(){}},api:{}};
vm.runInNewContext(source,context);
const plain=v=>JSON.parse(JSON.stringify(v));
const fixture=(values,value=0)=>{
 const old={name:'duration',value};
 const node={widgets:[old],__orvCapabilityStatus:{value:''},setDirtyCanvas(){},addWidget(type,name,value,callback,options){
  const item={type,name,value,callback,options,y:0,height:20,
   drawWidget(ctx){ctx.fillRect(15,0,370,20);ctx.fillText(`${this.label}  ${this.value}`,200,14);},
   onClick(e){this.setValue(e.position);},onDrag(e){this.setValue(e.position);},
  };Object.defineProperty(item,'height',{get(){return 20;}});this.widgets.push(item);return item;
 }};
 context.createDurationSlider(node,old);context.configureDuration(node,values);
 return {node,item:node.widgets[0]};
};
for(const [axis,values,expected] of [
 ['resolution',['480p','720p','1080p'],'720p'],['resolution',['1080p'],'1080p'],['resolution',['2K'],'2K'],
 ['resolution',['4K','480p'],'480p'],['aspect_ratio',['1:1','16:9'],'16:9'],['aspect_ratio',['1:1','4:3','9:16'],'4:3'],
 ['duration',[5,10],5],['duration',[4,6,8],4],['duration',Array.from({length:30},(_,i)=>i+1),1],
]) test(`supported product default ${axis} ${values}`,()=>assert.equal(context.productDefault(axis,values),expected));
test('confirmed default has precedence only inside confirmed domain',()=>{
 assert.equal(context.productDefault('duration',[4,6,8],8),8);
 assert.equal(context.productDefault('duration',[4,6,8],7),4);
 assert.equal(context.productDefault('resolution',null),null);
 assert.equal(context.productDefault('duration',[]),null);
 assert.equal(context.productDefault('size',['480x480']),null);
});
for(const values of [[5,10],[4,6,8],Array.from({length:30},(_,i)=>i+1),[1,2,5,10]]) test(`native bar maps drag/click only to seconds ${values.length}`,()=>{
 const {item}=fixture(values);
 assert.equal(item.type,'slider');assert.equal(item.value,values[0]);
 assert.equal(item.element,undefined);
 for(let p=-2;p<values.length+2;p+=0.13){item.onDrag({position:p});assert.ok(values.includes(item.value));assert.equal(item.serializeValue(),item.value);}
 for(let i=0;i<values.length;i++){item.onClick({position:i});assert.equal(item.value,values[i]);}
 const calls=[];item.drawWidget({fillRect(...args){calls.push(args);},fillText(text){calls.push(text);}}, {width:400});
 assert.equal(calls.at(-1),`Duration ${values.at(-1)}s`);
});
test('legacy zero migrates; explicit seconds save/reload; invalid switch defaults',()=>{
 const {node,item}=fixture([4,6,8],0);assert.equal(item.value,4);
 item.__orvSelectPosition(2);const saved=JSON.stringify({duration:item.serializeValue()});
 const reloaded=fixture([4,6,8],JSON.parse(saved).duration);assert.equal(reloaded.item.value,8);
 context.configureDuration(node,[5,10]);assert.equal(item.value,5);
 context.configureDuration(node,[5,10]);assert.equal(item.value,5);
 assert.equal(item.getExtraMenuOptions,undefined);
});
test('unknown capability is readonly and does not invent a default',()=>{
 const {item}=fixture(null,0);assert.equal(item.value,0);assert.equal(item.options.read_only,true);
 item.__orvSelectPosition(1);assert.equal(item.value,0);
});
test('direct native value writes snap to confirmed seconds, never indices',()=>{
 const {item}=fixture([4,6,8],4);
 assert.equal(item.options.min,4);assert.equal(item.options.max,8);
 item.value=5;assert.equal(item.serializeValue(),4);
 item.value=7;assert.equal(item.serializeValue(),6);
 item.value=2;assert.equal(item.serializeValue(),4);
 item.value=8;assert.equal(item.serializeValue(),8);
});
test('named fresh workflow with no selected method retains fields',()=>{
 const node={widgets:['model','inference_method','prompt','resolution','aspect_ratio','duration','size','seed','generate_audio'].map(name=>({name,value:null}))};
 assert.equal(context.restorePhase10NamedValues(node,{model:'SELECT MODEL',inference_method:'Select model first',prompt:'',duration:0,seed:-1,generate_audio:false}),true);
 assert.equal(node.widgets.find(x=>x.name==='prompt').value,'');
 assert.equal(node.widgets.find(x=>x.name==='seed').value,-1);
});
test('full reprojection resolves legacy defaults, preserves valid choices and method coupling',()=>{
 const node={inputs:[],__orvCapabilityStatus:{value:''},widgets:['model','inference_method','resolution','aspect_ratio','duration','size','generate_audio'].map(name=>({name,value:name==='inference_method'?'T2V':name==='duration'?0:name==='generate_audio'?false:'AUTO / MODEL DEFAULT'}))};
 const capability={supported_resolutions:['480p','720p','1080p'],supported_aspect_ratios:['1:1','16:9'],supported_durations:[4,6,8],supported_sizes:null,configuration_relations:[]};
 context.configureGenerationConfiguration(node,capability);
 const values=()=>Object.fromEntries(node.widgets.map(x=>[x.name,x.value]));
 assert.equal(values().resolution,'720p');assert.equal(values().aspect_ratio,'16:9');assert.equal(values().duration,4);assert.equal(values().size,'');
 node.widgets.find(x=>x.name==='duration').value=8;context.configureGenerationConfiguration(node,capability);assert.equal(values().duration,8);
 const relation={axes:['resolution','duration'],allowed:[{resolution:['720p'],duration:[4]}],forbidden:[],when:{inference_method:['I2V']},complete:true};
 node.widgets.find(x=>x.name==='inference_method').value='I2V';
 context.configureGenerationConfiguration(node,{...capability,configuration_relations:[relation]});
 assert.equal(values().duration,4);assert.equal(values().resolution,'720p');
});
test('legacy enums migrate, explicit valid values persist, Size stays optional',()=>{
 const node={widgets:[],__orvCapabilityStatus:{value:''}};
 for(const [name,values,expected] of [['resolution',['480p','720p'],'720p'],['aspect_ratio',['1:1','16:9'],'16:9'],['size',['480x480'],'']]){
  const item={name,value:'AUTO / MODEL DEFAULT'};node.widgets.push(item);context.configureEnum(node,item,values,name);
  assert.equal(item.value,expected);assert.ok(!item.options.values.includes('AUTO / MODEL DEFAULT'));
 }
 const res=node.widgets[0];res.value='480p';context.configureEnum(node,res,['480p','720p'],'RESOLUTION');assert.equal(res.value,'480p');
});
test('compact layout, explicit Size/control visibility and real block gap',()=>{
 const widgets=['model','inference_method','prompt','resolution','aspect_ratio','duration','seed','generate_audio','size','randomize'].map(name=>({name,hidden:false}));
 const node={widgets,computeSize(){return [900,500];},setSize(size){this.size=size;}};
 context.sizePrimaryControls(node);context.fitPresentationWidth(node);
 assert.equal(node.size[0],400);assert.equal(widgets[5].computeSize()[1],24);assert.equal(widgets[6].computeSize()[1],20);
 assert.equal(widgets[2].computeSize()[1],58);
 widgets[8].hidden=true;widgets[9].hidden=true;widgets[9].label='control after generate';
 context.syncAdvancedControls(node);assert.equal(widgets[8].hidden,true);assert.equal(widgets[9].hidden,false);
});
test('protected frontend functions retain immediate baseline definitions',()=>{
 const before=execFileSync('git',['show','a86df3bb825a04bc2852966b69ce65848b22de3b:web/openrouter_video.js'],{cwd:root,encoding:'utf8'});
 const functions=text=>Object.fromEntries(text.replace(/\r\n/g,'\n').split(/(?=^function |^async function )/m).slice(1).map(part=>[part.match(/function (\w+)/)[1],part.slice(0,part.indexOf('\n}')+2).split('\n').filter(line=>line.trim()).join('\n').trim()]));
 const allowed=new Set(['setVisible','addReadOnlyWidget','createGeometryCombos','sizePrimaryControls','stylePrompt','syncAdvancedControls','fitPresentationWidth','configureEnum','createDurationSlider','configureDuration','configureGenerationConfiguration','configureGeometry','normalizedValue','restorePhase10NamedValues','applyPresentation','bindEstimateRefresh','refreshEstimate']);
 const a=functions(before),b=functions(source);a.projectSelectedModel=a.projectSelectedModel.replace('setVisible(node.__orvAdvanced, Boolean(canonicalModel(node)));','setVisible(node.__orvAdvanced, false);');for(const name of Object.keys(a))if(!allowed.has(name))assert.equal(b[name],a[name],name);
 for(const file of ['src/openrouter_video/application.py','src/openrouter_video/capabilities.py','src/openrouter_video/client.py','src/openrouter_video/pricing.py']){
  assert.equal(readFileSync(new URL(file,root),'utf8').replace(/\r\n/g,'\n'),execFileSync('git',['show',`a86df3b:${file}`],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n'),file);
 }
});

