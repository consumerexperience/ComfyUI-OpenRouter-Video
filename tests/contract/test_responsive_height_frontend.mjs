import { reviewedRcText } from "./rc_reviewed_patch.mjs";
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import test from 'node:test';
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const c={app:{registerExtension(){}},api:{}};vm.runInNewContext(source,c);
function fixture(savedHeight=400){
 const n={size:[400,savedHeight],socketHeight:148,widgets:['model','inference_method','prompt','resolution','aspect_ratio','duration','seed','generate_audio','size','randomize'].map(name=>({name,value:name==='prompt'?'line one\nline two':null,hidden:false})),computeSize(){return [400,this.socketHeight+this.widgets.reduce((sum,w)=>sum+w.computeSize()[1]+4,0)+8];},setSize(size){this.size=size;this.__orvUserResizeActive=true;this.onResize?.(size);this.__orvUserResizeActive=false;}};
 c.sizePrimaryControls(n);c.installResponsiveHeight(n);c.fitPresentationWidth(n);return n;
}
function geometry(n){let y=n.socketHeight+2;const rows={};for(const w of n.widgets){rows[w.name]={y,height:w.computeSize()[1]};y+=w.computeSize()[1]+4;}return {rows,bottom:n.size[1]-y,prompt:rows.prompt.height-16};}
test('native content minimum, flexible delta, rigid bottom grid and clamp',()=>{
 const n=fixture();const min=n.computeSize()[1];n.setSize([400,min]);const a=geometry(n);
 for(const extra of [120,300,900,0]){n.setSize([400,min+extra]);const b=geometry(n);assert.equal(b.prompt-a.prompt,extra);assert.equal(b.bottom,a.bottom);assert.equal(b.rows.model.y,a.rows.model.y);for(const name of ['resolution','aspect_ratio','duration','seed','generate_audio','size','randomize'])assert.equal(b.rows[name].y-a.rows[name].y,extra);assert.equal(n.widgets[2].value,'line one\nline two');}
 n.setSize([400,1]);assert.equal(n.size[1],min);assert.equal(geometry(n).prompt,42);
});
test('socket topology/model reflow preserves height or grows measured minimum',()=>{
 const n=fixture(800);n.socketHeight+=120;c.fitPresentationWidth(n);assert.equal(n.size[1],920);const preferred=geometry(n).prompt;n.socketHeight+=700;c.fitPresentationWidth(n);assert.equal(n.size[1],1620);assert.equal(geometry(n).prompt,preferred);
});
test('saved tall and compact dimensions reconstruct without pixel persistence',()=>{
 for(const height of [400,800]){const n=fixture(height);const saved=JSON.parse(JSON.stringify({size:n.size,prompt:n.widgets[2].value}));const r=fixture(saved.size[1]);assert.deepEqual(Array.from(r.size),Array.from(n.size));assert.deepEqual(geometry(r),geometry(n));}
});

test('PUX03 user width survives model/socket/price reflow and restoration',()=>{
 const n=fixture(800);n.setSize([620,800]);
 for(const delta of [120,-60,200,-150]){n.socketHeight+=delta;c.fitPresentationWidth(n);assert.equal(n.size[0],620);}
 const saved=JSON.parse(JSON.stringify(n.size));n.size=saved;c.fitPresentationWidth(n);assert.equal(n.size[0],620);
 n.setSize([490,n.size[1]]);c.fitPresentationWidth(n);assert.equal(n.size[0],490);
});
test('PUX03 v1.1 content changes preserve preferred Prompt and anchored position',()=>{
 const n=fixture(800);n.pos=[51,73];n.setSize([620,920]);
 const prompt=geometry(n).prompt,baseHeight=n.size[1];
 for(const delta of [120,-120,300,-300]){
   const before=n.size[1];n.socketHeight+=delta;c.fitPresentationWidth(n);
   assert.equal(n.size[0],620);assert.equal(geometry(n).prompt,prompt);
   assert.equal(n.size[1],before+delta);assert.deepEqual(n.pos,[51,73]);
 }
 assert.equal(n.size[1],baseHeight);
});

test('PUX03 v1.1 delayed native onResize cannot become user intent',()=>{
 const n=fixture(800);n.setSize([620,920]);const preferred=n.__orvPreferredPromptExtra;
 for(const size of [[225,10],[900,1800],[400,442]]){
   n.size=size;n.onResize(size);assert.equal(n.__orvPreferredPromptExtra,preferred);
   assert.equal(n.size[0],620);assert.equal(n.size[1],n.computeSize()[1]+preferred);
 }
 c.app.canvas={resizing_node:n};n.size=[500,1000];n.onResize(n.size);
 assert.equal(n.__orvPreferredWidth,500);assert.equal(n.__orvPreferredPromptExtra,1000-n.computeSize()[1]);c.app.canvas=undefined;
});

test('PUX03 v1.1 native saved size reconstructs independent preferred geometry',()=>{
 const n=fixture(800);n.__orvRestoreGeometry=[610,970];c.fitPresentationWidth(n);
 const extra=n.__orvPreferredPromptExtra;assert.equal(n.size[0],610);assert.equal(n.size[1],970);
 n.socketHeight+=100;c.fitPresentationWidth(n);assert.equal(n.size[1],1070);assert.equal(n.__orvPreferredPromptExtra,extra);
 const other=fixture(500);assert.notEqual(other.__orvPreferredPromptExtra,extra);
 n.__orvRestoreGeometry=[100,1];c.fitPresentationWidth(n);assert.equal(n.size[0],225);assert.equal(n.__orvPreferredPromptExtra,0);
});

test('all non-layout source functions and protected values retain current baseline',()=>{
 const baseline=execFileSync('git',['show','25451ff:web/openrouter_video.js'],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}).replace(/\r\n/g,'\n').replace(/^import .*;\n/gm,'');
 const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));
 const a=functions(baseline),b=functions(reviewedRcText(new URL("../../",import.meta.url),"web/openrouter_video.js",source).replace(/^import .*;\r?\n/gm,""));for(const name of Object.keys(a))if(!['setVisible','addReadOnlyWidget','syncAdvancedControls','sizePrimaryControls','applyPresentation','fitPresentationWidth','configureGeometry','normalizedValue','configureGenerationConfiguration','restorePhase10NamedValues','bindEstimateRefresh','refreshEstimate'].includes(name))assert.equal(b[name],a[name],name);
 assert.equal(reviewedRcText(new URL('../../',import.meta.url),'web/openrouter_video.js',source).replace(/^import .*;\r?\n/gm,'').split('function widget')[0],baseline.split('function widget')[0]);
});
