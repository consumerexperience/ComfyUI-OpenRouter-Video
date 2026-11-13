import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import test from 'node:test';

const root=new URL('../../',import.meta.url);
const baseline='b6289127e7d2e6f735f6497e7e6cf0f26c5adcac';
const before=execFileSync('git',['show',`${baseline}:web/openrouter_video.js`],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n');
const current=readFileSync(new URL('web/openrouter_video.js',root),'utf8').replace(/\r\n/g,'\n');
const functions=t=>Object.fromEntries(t.split(/(?=^function |^async function )/m).slice(1).map(p=>[p.match(/function (\w+)/)[1],p.slice(0,p.indexOf('\n}')+2)]));
// Exact Owner-authorized interaction locations. Scalar, geometry, provider,
// billing, security and renderer functions are protected even within this file.
const allowed=new Set(['legacyReferenceKinds','reprojectNodeSemantics','parkIncompatibleMedia',
    'connectedReferenceKind','referencePrefix','moveInputToFrontPreservingLinks','addTrailingReferenceInput',
    'configureReferenceTopology','bindInferenceMethod','bindEstimateRefresh','projectSelectedModel']);
test('all existing functions outside OP07 catalogue delta, including OAuth/billing/renderer, are exact',()=>{
    const a=functions(before),b=functions(current);
    for(const [name,text] of Object.entries(a))if(!allowed.has(name))assert.equal(b[name],text,name);
    const registration=text=>text.split('app.registerExtension({')[1];
    assert.equal(registration(current).split('    async beforeRegisterNodeDef')[0],
        registration(before).split('    async beforeRegisterNodeDef')[0], 'settings and lifecycle setup');
    const created=text=>text.split('        const previousCreated =')[1].split('        const previousConfigure =')[0];
    assert.equal(created(current),created(before),'node creation, outputs, widgets and rendering');
    const configured=text=>text.split('        const previousConfigure =')[1];
    assert.equal(configured(current)
        .replace('            delete this.__orvPendingMediaSelection;\n','')
        .replace('            this.__orvConfiguringMedia = true;\n','')
        .replace('            this.__orvProjectionVersion = (this.__orvProjectionVersion || 0) + 1;\n','')
        .replace('            const configuringVersion = this.__orvConfigureVersion = (this.__orvConfigureVersion || 0) + 1;\n','')
        .replace('                if (this.__orvConfigureVersion !== configuringVersion) return;\n','')
        .replace('                this.__orvConfiguringMedia = false;\n',''),
        configured(before),'workflow restore only guards link reconstruction and clears selection authority');
});
test('no browser credentials, queue, inference or new transport introduced',()=>{
    assert(!/localStorage|sessionStorage|indexedDB|Authorization\s*:/.test(current));
    assert(!current.includes('/api/v1/videos'));
    assert(!current.includes('api.queuePrompt'));
});
