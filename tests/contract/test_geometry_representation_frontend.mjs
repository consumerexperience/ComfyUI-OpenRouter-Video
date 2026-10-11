import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=readFileSync(new URL('../../web/openrouter_video.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
const c={app:{registerExtension(){}},api:{}};vm.runInNewContext(source,c);
const both={supported_resolutions:['720p','1080p'],supported_aspect_ratios:['16:9','9:16'],supported_sizes:['1280x720','720x1280']};
function node(size=''){return {widgets:['resolution','aspect_ratio','size'].map(name=>({name,value:name==='size'?size:name==='resolution'?'720p':'16:9',options:{}}))};}
test('both domains default normalized; alternate disclosure reveals size',()=>{const n=node();c.configureGeometry(n,both);assert.equal(n.widgets[2].hidden,true);assert.equal(n.__orvGeometryAlternative,true);n.__orvShowExact=true;c.configureGeometry(n,both);assert.equal(n.widgets[2].hidden,false);});
test('legacy explicit size activates exact, clears inactive normalized values without mapping',()=>{const n=node('720x1280');c.configureGeometry(n,both);assert.equal(n.widgets[2].value,'720x1280');assert.equal(n.widgets[0].value,'');assert.equal(n.widgets[1].value,'');assert.equal(n.widgets[0].hidden,true);assert.equal(n.widgets[1].hidden,true);const saved=JSON.parse(JSON.stringify(n));c.configureGeometry(saved,both);assert.equal(saved.widgets[2].value,'720x1280');assert.equal(saved.widgets[0].value,'');});
test('clearing exact switches back to confirmed normalized defaults',()=>{const n=node('1280x720');c.configureGeometry(n,both);n.widgets[2].value='';c.configureGeometry(n,both);assert.equal(n.widgets[0].value,'720p');assert.equal(n.widgets[1].value,'16:9');assert.equal(n.widgets[2].value,'');});
test('size-only domain offers exact selection without normalized controls',()=>{const n=node();c.configureGeometry(n,{...both,supported_resolutions:[],supported_aspect_ratios:[]});assert.equal(n.widgets[0].hidden,true);assert.equal(n.widgets[1].hidden,true);assert.equal(n.widgets[2].hidden,false);assert.equal(n.widgets[2].value,'');});
test('normalized-only domain has no competing size',()=>{const n=node();c.configureGeometry(n,{...both,supported_sizes:[]});assert.equal(n.widgets[0].hidden,false);assert.equal(n.widgets[1].hidden,false);assert.equal(n.widgets[2].hidden,true);});
