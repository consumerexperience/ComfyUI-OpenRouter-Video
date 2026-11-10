import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import test from 'node:test';

const root=new URL('../../',import.meta.url);
const baseline='058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9';
const before=execFileSync('git',['show',`${baseline}:web/openrouter_video.js`],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n');
const current=readFileSync(new URL('web/openrouter_video.js',root),'utf8').replace(/\r\n/g,'\n');
const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));
const allowed=new Set(['setConnectionPresentation','loadCapabilities','configureModelPicker','projectSelectedModel','reprojectNodeSemantics','configurationScope','fixedRolesForMethod','configureReferenceTopology','refreshEstimate','methodUsesReferences']);
test('all existing functions outside OP07 catalogue delta, including OAuth/billing/renderer, are exact',()=>{
    const a=functions(before),b=functions(current);
    for(const [name,text] of Object.entries(a))if(!allowed.has(name))assert.equal(b[name],text,name);
    // Registration/renderer hooks only gain lifecycle setup; no changes to
    // onConfigure/onNodeCreated, widget serialization or node definitions.
    assert.equal(current.split('app.registerExtension({')[1].replace('        startCatalogueLifecycle();\n',''),before.split('app.registerExtension({')[1]);
});
test('no browser credentials, queue, inference or new transport introduced',()=>{
    assert(!/localStorage|sessionStorage|indexedDB|Authorization\s*:/.test(current));
    assert(!current.includes('/api/v1/videos'));
    assert(!current.includes('api.queuePrompt'));
});
