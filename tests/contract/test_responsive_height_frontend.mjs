import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import test from 'node:test';
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const c={app:{registerExtension(){}},api:{}};vm.runInNewContext(source,c);
function fixture(savedHeight=400){
 const n={size:[400,savedHeight],socketHeight:148,widgets:['model','inference_method','prompt','resolution','aspect_ratio','duration','seed','generate_audio','size','randomize'].map(name=>({name,value:name==='prompt'?'line one\nline two':null,hidden:false})),computeSize(){return [400,this.socketHeight+this.widgets.reduce((sum,w)=>sum+w.computeSize()[1]+4,0)+8];},setSize(size){this.size=size;this.onResize?.(size);}};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);return n;
}
function geometry(n){let y=n.socketHeight+2;const rows={};for(const w of n.widgets){rows[w.name]={y,height:w.computeSize()[1]};y+=w.computeSize()[1]+4;}return {rows,bottom:n.size[1]-y,prompt:rows.prompt.height-16};}
test('native content minimum, flexible delta, rigid bottom grid and clamp',()=>{
 const n=fixture();const min=n.computeSize()[1];n.setSize([400,min]);const a=geometry(n);
 for(const extra of [120,300,900,0]){n.setSize([400,min+extra]);const b=geometry(n);assert.equal(b.prompt-a.prompt,extra);assert.equal(b.bottom,a.bottom);assert.equal(b.rows.model.y,a.rows.model.y);for(const name of ['resolution','aspect_ratio','duration','seed','generate_audio','size','randomize'])assert.equal(b.rows[name].y-a.rows[name].y,extra);assert.equal(n.widgets[2].value,'line one\nline two');}
 n.setSize([400,1]);assert.equal(n.size[1],min);assert.equal(geometry(n).prompt,42);
});
test('socket topology/model reflow preserves height or grows measured minimum',()=>{
 const n=fixture(800);n.socketHeight+=120;c.fitPresentationWidth(n);assert.equal(n.size[1],800);assert.equal(geometry(n).prompt,42+800-n.computeSize()[1]);n.socketHeight+=700;c.fitPresentationWidth(n);assert.equal(n.size[1],n.computeSize()[1]);assert.equal(geometry(n).prompt,42);
});
test('saved tall and compact dimensions reconstruct without pixel persistence',()=>{
 for(const height of [400,800]){const n=fixture(height);const saved=JSON.parse(JSON.stringify({size:n.size,prompt:n.widgets[2].value}));const r=fixture(saved.size[1]);assert.deepEqual(r.size,n.size);assert.deepEqual(geometry(r),geometry(n));}
});
test('all non-layout source functions and protected values retain current baseline',()=>{
 const baseline=execFileSync('git',['show','25451ff:web/openrouter_video.js'],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}).replace(/\r\n/g,'\n').replace(/^import .*;\n/gm,'');
 const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));
 const a=functions(baseline),b=functions(source);for(const name of Object.keys(a))if(!['setVisible','addReadOnlyWidget','syncAdvancedControls','sizePrimaryControls','applyPresentation','fitPresentationWidth','configureGeometry','configureGenerationConfiguration'].includes(name))assert.equal(b[name],a[name],name);
 assert.equal(source.split('function widget')[0],baseline.split('function widget')[0]);
});
