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
test('Size and workflow control are intentional primary, not renderer advanced accident',()=>{
 const c=context();const n={widgets:[{name:'size',hidden:true,options:{advanced:true}},{name:'randomize',label:'control after generate',hidden:true,options:{advanced:true}}]};c.syncAdvancedControls(n);for(const w of n.widgets){assert.equal(w.options.advanced,false);assert.equal(w.hidden,false);assert.equal(w.options.hidden,false);}
});
test('estimate is plain presentation state, no COST widget or serializer slot',()=>{
 const c=context();const state=c.createEstimateState();state.value='≈ $1.60 EST.';assert.equal(state.value,'≈ $1.60 EST.');assert.equal(state.type,undefined);assert.equal(state.serializeValue,undefined);assert.ok(!source.includes('addReadOnlyWidget(\n                this,\n                "COST"'));assert.ok(source.includes('this.__orvEstimate = createEstimateState()'));
});
function domFixture(){
 const marks=[];const textarea={rows:5};const plain={querySelector(){return null;},classList:{add(){}}};const prompt={querySelector(){return textarea;},classList:{add(s){marks.push(s);}}};
 const grid={style:{},querySelectorAll(){return [plain,plain,prompt,plain,plain,plain,plain,plain,plain];}};
 const header={children:[],querySelector(){return this.children[0];},append(x){this.children.push(x);}};
 const element={dataset:{nodeId:'22'},classList:{add(s){marks.push(s);}},querySelector(s){return s.startsWith('.lg-node-header')?header:grid;}};
 const document={querySelectorAll(){return [element];},createElement(){return {textContent:'',title:''};}};
 const c=context({document});const n={id:22,__orvEstimate:{value:'≈ $1.60 EST.'}};return {c,n,header,grid,textarea,marks};
}
test('Beta estimate is one header child, updates unavailable, never body overlay',()=>{
 const {c,n,header}=domFixture();c.syncBetaPresentation(n);c.syncBetaPresentation(n);assert.equal(header.children.length,1);assert.equal(header.children[0].textContent,'≈ $1.60 EST.');n.__orvEstimate.value='ESTIMATE UNAVAILABLE';c.syncBetaPresentation(n);assert.equal(header.children.length,1);assert.equal(header.children[0].title,'ESTIMATE UNAVAILABLE');assert.ok(!source.includes('position:absolute'));
});
test('native Beta grid reserves only Prompt as flex; rows are not stretched',()=>{
 const {c,n,grid,textarea}=domFixture();c.syncBetaPresentation(n);assert.equal(grid.style.flex,'1 1 auto');assert.equal(grid.style.gridTemplateRows.split('minmax').length,2);assert.equal(grid.style.gridTemplateRows.split('max-content').length,9);assert.equal(textarea.rows,2);c.syncBetaPresentation(n);assert.equal(textarea.rows,2);
});
test('Classic canvas remains untouched when Vue DOM is absent',()=>{
 const c=context({document:{querySelectorAll:()=>[]}});assert.doesNotThrow(()=>c.syncBetaPresentation({id:22}));
});
test('renderer adapter cleans node ownership and shares one observer',()=>{
 let observers=0;const scheduled=[];const document={head:{append(){}},body:{},querySelectorAll:()=>[],createElement:()=>({})};const c=context({document,MutationObserver:class {constructor(){observers++;}observe(){}},queueMicrotask:fn=>scheduled.push(fn)});const a={},b={};c.installBetaPresentation(a);c.installBetaPresentation(a);c.installBetaPresentation(b);assert.equal(observers,1);assert.equal(c.installBetaPresentation.nodes.size,2);assert.equal(scheduled.length,1);scheduled.shift()();a.onRemoved();assert.equal(c.installBetaPresentation.nodes.size,1);b.onRemoved();assert.equal(c.installBetaPresentation.nodes.size,0);
});
test('all semantic/frontend functions and Python source exactly match immediate baseline',()=>{
 const before=execFileSync('git',['show','e89b513:web/openrouter_video.js'],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n').replace(/^import .*;\n/gm,'');const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));const a=functions(before),b=functions(source);for(const name of Object.keys(a))if(!['setVisible','addReadOnlyWidget','applyPresentation','syncAdvancedControls'].includes(name))assert.equal(b[name],a[name],name);assert.equal(source.split('function widget')[0],before.split('function widget')[0]);
 for(const file of execFileSync('git',['ls-tree','-r','--name-only','e89b513','src'],{cwd:root,encoding:'utf8'}).trim().split('\n'))assert.equal(readFileSync(new URL(file,root),'utf8').replace(/\r\n/g,'\n'),execFileSync('git',['show',`e89b513:${file}`],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n'),file);
});
