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
function domFixture(){
 const marks=[];const textarea={rows:5,placeholder:'Prompt'};const plain={querySelector(){return null;},classList:{add(){}}};const prompt={querySelector(s){return s==='textarea'?textarea:null;},classList:{add(s){marks.push(s);}}};
 const grid={style:{},querySelectorAll(){return [plain,plain,prompt,plain,plain,plain,plain,plain,plain];}};
 const header={children:[],querySelector(){return this.children[0];},append(x){this.children.push(x);}};
 const element={dataset:{nodeId:'22'},classList:{add(s){marks.push(s);}},querySelector(s){return s.startsWith('.lg-node-header')?header:grid;}};
 const document={querySelectorAll(){return [element];},createElement(){return {style:{},textContent:'',title:'',setAttribute(name,value){this[name]=value;},addEventListener(){}};}};
 const c=context({document});const n={id:22,__orvEstimate:{value:'≈ $1.60 EST.'}};return {c,n,header,grid,textarea,marks};
}
test('Beta estimate is one header child, updates unavailable, never body overlay',()=>{
 const {c,n,header}=domFixture();c.syncBetaPresentation(n);c.syncBetaPresentation(n);assert.equal(header.children.length,1);assert.equal(header.children[0].textContent,'≈ $1.60 EST.');n.__orvEstimate.value='ESTIMATE UNAVAILABLE';c.syncBetaPresentation(n);assert.equal(header.children.length,1);assert.equal(header.children[0].title,'');assert.ok(header.children[0]['aria-label']);assert.equal(header.children[0].role,'button');assert.equal(header.children[0].tabIndex,0);assert.ok(!source.includes('position:absolute'));
});
test('native Beta grid reserves only Prompt as flex; rows are not stretched',()=>{
 const {c,n,grid,textarea}=domFixture();c.syncBetaPresentation(n);assert.equal(grid.style.flex,'1 1 auto');assert.equal(grid.style.gridTemplateRows.split('minmax').length,2);assert.equal(grid.style.gridTemplateRows.split('max-content').length,9);assert.equal(textarea.rows,2);c.syncBetaPresentation(n);assert.equal(textarea.rows,2);
});
test('Classic canvas remains untouched when Vue DOM is absent',()=>{
 const c=context({document:{querySelectorAll:()=>[]}});assert.doesNotThrow(()=>c.syncBetaPresentation({id:22}));
});

test('PUX03 advanced textareas never compete with Prompt for flexible height',()=>{
 const {c,n,grid}=domFixture(),marks=[];
 const advanced={rows:5,placeholder:'negative_prompt'},promptArea={rows:2,placeholder:'Prompt'};
 const row=(area)=>({querySelector(s){return s==='textarea'?area:null;},classList:{add(v){marks.push([area.placeholder,v])},remove(){}}});
 grid.querySelectorAll=()=>[row(advanced),row(promptArea),row({rows:3,placeholder:'provider notes'})];
 c.syncBetaPresentation(n);assert.equal(grid.style.gridTemplateRows,'max-content minmax(42px, 1fr) max-content');
 assert.equal(advanced.rows,5);assert.deepEqual(marks,[['Prompt','orv-prompt-row']]);
 grid.querySelectorAll=()=>[row(advanced)];c.syncBetaPresentation(n);assert.equal(grid.style.flex,'');
});
test('PUX05 capacity presentation preserves every quantity and uncertainty across widths and locale',()=>{
 const c=context(),n={__orvReferenceSummary:'4 connected · image 2 · video 1 · audio 1 · 46 remaining · IMAGE 28 available · VIDEO 9 available · AUDIO 9 available · 2 parked'};
 const original=n.__orvReferenceSummary;
 const text=c.capacitySummaryText(n);assert(text.startsWith('4 connected · 46 remaining · 2 parked'));
 for(const width of [220,340,620,1000]){const lines=Array.from(c.capacitySummaryLines(n,width));assert.equal(lines.join(' '),text);assert(lines.every(line=>line.length<=Math.floor((width-24)/8)));}
 assert(c.capacitySummaryLines(n,1000).length<c.capacitySummaryLines(n,220).length);
 c.app.ui={settings:{getSettingValue:()=> 'ru'}};assert(c.capacitySummaryText(n).includes('2 сохранено вне режима'));
 n.__orvReferenceSummary='0 connected · verified subset boundary · upper bound unverified · VIDEO capacity unverified';
 assert(c.capacitySummaryText(n).includes('ёмкость не подтверждена'));assert(!c.capacitySummaryText(n).includes('доступно'));
 n.__orvReferenceSummary=original;assert.equal(n.__orvReferenceSummary,original);
});

test('PUX05 Nodes2 wraps one nonserialized summary without replacing the native widget',()=>{
 const {c,n,grid}=domFixture(),input={style:{}},children=[];
 n.__orvReferenceSummary='4 connected · 46 remaining · 2 parked';n.__orvSummary={name:'REFERENCES',serialize:false,value:n.__orvReferenceSummary};const widget=n.__orvSummary;
 const row={querySelector(s){return s==='input[aria-label="REFERENCES"]'?input:s==='.orv-capacity-summary'?children[0]:null;},append(item){children.push(item);}};
 grid.querySelectorAll=()=>[row];c.syncBetaPresentation(n);c.syncBetaPresentation(n);
 assert.equal(children.length,1);assert.equal(children[0].textContent,c.capacitySummaryText(n));assert.equal(input.style.display,'none');
 assert.equal(children[0].style.whiteSpace,'normal');assert.equal(n.__orvSummary,widget);assert.equal(widget.serialize,false);
});

test('renderer adapter cleans node ownership and shares one observer',()=>{
 let observers=0;const scheduled=[];const document={head:{append(){}},body:{},querySelectorAll:()=>[],createElement:()=>({})};const c=context({document,MutationObserver:class {constructor(){observers++;}observe(){}},queueMicrotask:fn=>scheduled.push(fn)});const a={},b={};c.installBetaPresentation(a);c.installBetaPresentation(a);c.installBetaPresentation(b);assert.equal(observers,1);assert.equal(c.installBetaPresentation.nodes.size,2);assert.equal(scheduled.length,1);scheduled.shift()();a.onRemoved();assert.equal(c.installBetaPresentation.nodes.size,1);b.onRemoved();assert.equal(c.installBetaPresentation.nodes.size,0);
});
test('all semantic/frontend functions and Python source exactly match immediate baseline',()=>{
 const before=execFileSync('git',['show','e89b513:web/openrouter_video.js'],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n').replace(/^import .*;\n/gm,'');const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));const a=functions(before),b=functions(reviewedRcText(new URL("../../",import.meta.url),"web/openrouter_video.js",source).replace(/^import .*;\r?\n/gm,""));for(const name of Object.keys(a))if(!['setVisible','addReadOnlyWidget','applyPresentation','syncAdvancedControls','configureGeometry','normalizedValue','configureGenerationConfiguration','restorePhase10NamedValues','bindEstimateRefresh','refreshEstimate'].includes(name))assert.equal(b[name],a[name],name);assert.equal(reviewedRcText(new URL('../../',import.meta.url),'web/openrouter_video.js',source).replace(/^import .*;\r?\n/gm,'').split('function widget')[0],before.split('function widget')[0]);
 for(const file of execFileSync('git',['ls-tree','-r','--name-only','e89b513','src'],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(file=>!['src/openrouter_video/models.py','src/openrouter_video/comfy/nodes.py','src/openrouter_video/comfy/projection.py','src/openrouter_video/comfy/routes.py','src/openrouter_video/secrets.py','src/openrouter_video/oauth.py'].includes(file)))assert.equal(reviewedRcText(root,file,readFileSync(new URL(file,root),'utf8')).replace(/\r\n/g,'\n'),execFileSync('git',['show',`e89b513:${file}`],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n'),file);
});
