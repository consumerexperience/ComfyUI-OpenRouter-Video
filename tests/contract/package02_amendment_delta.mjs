// Exact proposed Package02 delta. No acceptance implied; historical pins stay immutable.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const base='0e55e984471ad8a8aecc91d8bd580ea3856520d8';
const normalize=s=>s.replace(/\r\n/g,'\n');
const sha=s=>createHash('sha256').update(normalize(s)).digest('hex');
function body(text,name){
 const start=new RegExp(`^(?:async )?function ${name}\\(`,'m').exec(text);assert(start,name);
 const a=start.index,e=text.indexOf('\n',a),line=text.slice(a,e).trimEnd();
 if(line.endsWith('}'))return text.slice(a,e+1);
 const end=/^\}\n/m.exec(text.slice(e+1));assert(end,name);return text.slice(a,e+1+end.index+end[0].length);
}
// Final Owner corrections normalize to the exact already reviewed predecessor.
// The historical checker below still enforces the older Package 02 gates.
function finalOwnerPredecessor(root,path,current){
 if(path!=='web/openrouter_video.js' || sha(current)!=='694be0598cfdbe3edf7b40c9ce5e4b87063a7f945fd01e27a94e67ca2685765a')return current;
 const before=normalize(execFileSync('git',['show','769bc62a74855e8b3096a225101bd85b791abf57:'+path],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),'77d398eaf04333c6de1a43e4187c653cd6ca5412efa3f33ecf3665c95aeefb3f');
 const changed=['bindEstimateRefresh','configureDuration','configureOperationControls','createDurationSlider','installParameterColumns','providerDisplayValue','sizePrimaryControls','syncBetaPresentation','syncProviderNumericState'];
 const added=['installClassicProviderSlider','syncDurationSliderState','syncNumericAutoButton'];
 let restored=normalize(current);
 for(const name of changed)restored=restored.replace(body(restored,name),()=>body(before,name));
 for(const name of added){
  const text=body(restored,name)+'\n';
  assert(restored.includes(text),name);
  restored=restored.replace(text,'');
 }
 assert.equal(restored,before,'Only final Owner numeric, spacing and adaptive Duration functions may differ');
 return before;
}
// Extend the scope gate without changing historical baseline fixtures.
function stableVuePredecessor(root,path,current){
 if(path!=='web/openrouter_video.js' || sha(current)!=='f2f9c8f150a2ceebd89846f93c6fe4a8eec1fbf99f01154616ed52974f67ef4a')return current;
 const before=normalize(execFileSync('git',['show','a720d1d2cfb5fa29360daf3760374ad4d4720058:'+path],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),'694be0598cfdbe3edf7b40c9ce5e4b87063a7f945fd01e27a94e67ca2685765a');
 let restored=normalize(current);
 for(const name of ['fitPresentationWidth','installBetaPresentation','syncBetaPresentation'])restored=restored.replace(body(restored,name),()=>body(before,name));
 assert.equal(restored,before,'Only Vue layout ownership and sizing may differ');
 return before;
}
function nativeShrinkPredecessor(root,path,current){
 if(path!=='web/openrouter_video.js' || sha(current)!=='a226f2d08b4b78f9e3563f87b9d5780c1e6a0729cda6f1155d6a5569d3f1ac8b')return current;
 const before=normalize(execFileSync('git',['show','5a522076592ba81a20ef11ab46bb2a352c6bd342:'+path],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),'f2f9c8f150a2ceebd89846f93c6fe4a8eec1fbf99f01154616ed52974f67ef4a');
 let restored=normalize(current);
 for(const name of ['installBetaPresentation','syncBetaPresentation'])restored=restored.replace(body(restored,name),()=>body(before,name));
 assert.equal(restored,before,'Only the Nodes 2.0 native resize probe may differ');
 return before;
}
const finalAciBase = 'd3dcc6e1982ea6da901afd49b42432bb25deaa5c';
const finalAciPricingPaths = ['src/openrouter_video/data/video-tariff-rules.json','src/openrouter_video/pricing.py'];
function finalAciPredecessor(root,path,current) {
 const pin=JSON.parse(readFileSync(new URL('tests/fixtures/package02-final-aci-source-candidate.json',root),'utf8'));
 if(pin.files[path]?.candidate_sha256!==sha(current))return current;
 assert.equal(pin.baseline,finalAciBase);
 assert.equal(pin.status,'UNACCEPTED_FINAL_ACI');
 assert.deepEqual(Object.keys(pin.files).sort(),[...finalAciPricingPaths,'web/openrouter_video.js'].sort());
 const before=normalize(execFileSync('git',['show',finalAciBase+':'+path],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),pin.files[path].baseline_sha256);
 if(path==='web/openrouter_video.js') {
  let restored=normalize(current);
  for(const name of ['costText','costTooltipView','costPriceView','costTechnicalDetailsText','syncClassicCostBadge'])
    restored=restored.replace(body(restored,name),()=>body(before,name));
  assert.equal(restored,before,'Only financial copy and rate presentation may differ');
 }
 return before;
}
export function finalAciBackendPaths(root) {
 return finalAciPricingPaths.filter(path=>{
  const raw=readFileSync(new URL(path,root),'utf8');
  return finalAciPredecessor(root,path,raw)!==raw;
 });
}
function parkedCopyPredecessor(root,path,current) {
 if(path!=='web/openrouter_video.js' || sha(current)!=='ed09a62c12e94ff5a69e1790d52a00d50aa2b2dbc36c21b082eec09671089930')return current;
 const before=normalize(execFileSync('git',['show','416c8d55b99133c5e448c91c5753c200630fa8c9:'+path],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),'1912d066ab889a8b0dc8224461cdeecf58ae3c714bde6ba976ec24d5209258c6');
 let restored=normalize(current);
 for(const name of ['drawCapacityMeter','syncCapacityMeter','capacitySummaryText','reconcileReferenceTopology'])
  restored=restored.replace(body(restored,name),()=>body(before,name));
 for(const name of ['parkedReferenceLabel','parkedReferenceTooltip'])
  restored=restored.replace(body(restored,name)+'\n','');
 assert.equal(restored,before,'Only Parked labels and existing tooltip text may differ');
 return before;
}
function tooltipRefinementPredecessor(root,path,current) {
 if(path!=='web/openrouter_video.js' || sha(current)!=='7e8fd8899f359e8b06fadcfb8c229abd18d20b1998c3b70ee73f81fc03b81654')return current;
 const parent='c54b8ffd902cef1d5efce7e36a14062c1847fc86';
 const before=normalize(execFileSync('git',['show',parent+':'+path],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),'ed09a62c12e94ff5a69e1790d52a00d50aa2b2dbc36c21b082eec09671089930');
 let restored=normalize(current);
 for(const name of ['costText','costValidationSection','costTooltipView','renderCostDetails','costDetailsText'])
  restored=restored.replace(body(restored,name),()=>body(before,name));
 for(const name of ['costUnknownOutputTokenQuantity','costRateCondition'])restored=restored.replace(body(restored,name)+'\n','');
 assert.equal(restored,before,'Only tooltip copy, diagnostics and existing tooltip layout may differ');
 return before;
}
export function providerIsolationPredecessor(root, path, current) {
 if (path !== 'web/openrouter_video.js') return current;
 if (sha(current) !== 'd9a996deaa11a423ba03d5a63f652908b18c834facab7febdd3f97d0c05d548b') return current;
 const parent = '551781a9079afc092d33fe8859c4e611a519c120';
 const before = normalize(execFileSync('git', ['show', parent + ':' + path], {cwd:root, encoding:'utf8'}));
 assert.equal(sha(before), '7e8fd8899f359e8b06fadcfb8c229abd18d20b1998c3b70ee73f81fc03b81654');
 const replacements = [
  [
   '            setVisible(item, false);\n            if (item.name?.startsWith("provider_option:")) item.options.serialize = false;\n',
   '            setVisible(item, false);\n',
  ],
  [
   '        // Inline provider values travel through provider_options. Comfy\n' +
   '        // serializes connected STRING sockets separately from their widgets.\n' +
   '        Object.assign(item.options ||= {}, {min:spec.min, max:spec.max, serialize:false});\n',
   '        Object.assign(item.options ||= {}, {min:spec.min, max:spec.max});\n',
  ],
  [
   '            for (const item of this.widgets || []) {\n' +
   '                if (!item.name?.startsWith("provider_option:")) continue;\n' +
   '                setVisible(item, false);\n' +
   '                item.options.serialize = false;\n' +
   '            }\n',
   '            for (const item of this.widgets || []) if (item.name?.startsWith("provider_option:")) setVisible(item,false);\n',
  ],
 ];
 let restored = normalize(current);
 for (const [after, prior] of replacements) {
  assert.equal(restored.split(after).length, 2);
  restored = restored.replace(after, () => prior);
 }
 assert.equal(restored, before, 'Only provider widget serialization may differ from the prior TEST frontend');
 return before;
}
function financialBadgeStandardPredecessor(root, path, current) {
 if (path !== 'web/openrouter_video.js' ||
     sha(current) !== '29fcd0386820b9a492f74659be0741f9f9cbf21e20ed8a8837405de4f26994f8') return current;
 const parent = '0cceea15c1c51c74d9166e78fc2b0978025daccb';
 const before = normalize(execFileSync('git', ['show', parent + ':' + path], {cwd:root, encoding:'utf8'}));
 assert.equal(sha(before), 'd9a996deaa11a423ba03d5a63f652908b18c834facab7febdd3f97d0c05d548b');
 let restored = normalize(current);
 for (const name of ['costText', 'costPriceView', 'costBadgeColors']) {
  restored = restored.replace(body(restored, name), () => body(before, name));
 }
 assert.equal(restored, before, 'Only approved financial badge presentation can differ');
 return before;
}
function integratedAciPredecessor(root, path, current) {
 if (path !== 'web/openrouter_video.js' ||
     sha(current) !== '38fc6fb5e95f9b9e7e0c8bbe07bbd259bf5668453f2b41ad4377fed80da5f128') return current;
 const before = normalize(execFileSync('git', ['show', '70dd97c691081a247c906ecd63d1defe80bf5773:' + path],
     {cwd:root, encoding:'utf8'}));
 assert.equal(sha(before), '29fcd0386820b9a492f74659be0741f9f9cbf21e20ed8a8837405de4f26994f8');
 let restored = normalize(current);
 const pricing = '        // A connected creative input overrides the stored value at execution.\n' +
     '        // Its text (and length) are unavailable to the pricing preview.\n' +
     '        const creative = ["negative_prompt", "creative_prompt"].includes(spec?.text_semantic);\n' +
     '        const socketName = `provider_option:${option.provider}:${spec?.container || ""}:${option.key}`;\n' +
     '        if (creative && inputByName(node, socketName)?.link != null) continue;\n';
 const connection = '            const creativeInputChanged = args[4]?.name?.startsWith("provider_option:");\n' +
     '            if (hasMedia || creativeInputChanged) {';
 for (const [added, prior] of [[pricing,''], [connection,'            if (hasMedia) {']]) {
  assert.equal(restored.split(added).length, 2);
  restored = restored.replace(added, () => prior);
 }
 assert.equal(restored, before, 'Only the approved linked creative pricing correction can differ');
 return before;
}
function resizeBoundaryAndActualPredecessor(root, path, current) {
 if (path !== 'web/openrouter_video.js' ||
     sha(current) !== 'd0be4884a9e4620313f2abc5f0003ca99e8eeec4ad29a1485f7ec22a60d9bad5') return current;
 const before = normalize(execFileSync('git', ['show', '025e3cda3e50f6ca035ef628b93fd32e50e55937:' + path],
     {cwd:root, encoding:'utf8'}));
 assert.equal(sha(before), '38fc6fb5e95f9b9e7e0c8bbe07bbd259bf5668453f2b41ad4377fed80da5f128');
 let restored = normalize(current);
 const intent = body(restored, 'actualIntentKey');
 restored = restored.replace(intent + '\n', '');
 for (const name of ['syncBetaPresentation', 'configureOperationControls', 'resetActualBinding', 'actualOwnersForQueuedPrompt',
     'costBadgeLabel', 'handleActualExecuted', 'syncClassicCostBadge', 'bindEstimateRefresh']) {
  restored = restored.replace(body(restored, name), () => body(before, name));
 }
 assert.equal(restored, before, 'Only the approved Nodes 2.0 boundary and ACTUAL header remediation can differ');
 return before;
}
function sharedResizeFloorPredecessor(root, path, current) {
 if (path !== 'web/openrouter_video.js' ||
     sha(current) !== 'b89133aa012369f0e2f5bde118409ba206714a42d39624c484e0f35684d633ae') return current;
 const before = normalize(execFileSync('git', ['show', '2dee70f7e36d96393202d81d2e8093417950bc8b:' + path],
     {cwd:root, encoding:'utf8'}));
 assert.equal(sha(before), 'd0be4884a9e4620313f2abc5f0003ca99e8eeec4ad29a1485f7ec22a60d9bad5');
 let restored = normalize(current);
 for (const name of ['installBetaPresentation', 'syncBetaPresentation']) {
  restored = restored.replace(body(restored, name), () => body(before, name));
 }
 assert.equal(restored, before, 'Only the approved shared Nodes 2.0 resize floor can differ');
 return before;
}
export function package02AmendmentBaselineSource(root,path,current){
 current=sharedResizeFloorPredecessor(root,path,current);
 current=resizeBoundaryAndActualPredecessor(root,path,current);
 current=integratedAciPredecessor(root,path,current);
 current=financialBadgeStandardPredecessor(root,path,current);
 current=providerIsolationPredecessor(root,path,current);
 current=tooltipRefinementPredecessor(root,path,current);
 current=parkedCopyPredecessor(root,path,current);
 current=finalAciPredecessor(root,path,current);
 current=nativeShrinkPredecessor(root,path,current);
 current=stableVuePredecessor(root,path,current);
 current=finalOwnerPredecessor(root,path,current);
 const pin=JSON.parse(readFileSync(new URL('tests/fixtures/package02-amendments-source-candidate.json',root),'utf8'));
 if(!pin.files[path] || sha(current)!==pin.files[path])return current;
 assert.equal(pin.status,'UNACCEPTED_PACKAGE02_FINAL_12');assert.equal(pin.baseline,base);
 const before=normalize(execFileSync('git',['show',`${base}:${path}`],{cwd:root,encoding:'utf8'}));assert.equal(sha(before),pin.baseline_files[path]);
 if(path==='web/openrouter_video.js'){
  const allowed=["applyPresentation", "bindEstimateRefresh", "configureDuration", "configureOperationControls", "costAdvisoryComparison", "costText", "costTooltipView", "drawCapacityMeter", "drawCollapsedCostBadge", "drawReadOnlyValue", "fitPresentationWidth", "installBetaPresentation", "installParameterColumns", "installResponsiveHeight", "nativeFlowHeight", "orderPresentationWidgets", "providerObjectIssue", "renderCostDetails", "scheduleBetaPresentation", "sizePrimaryControls", "restorePhase10NamedValues", "restorePhase10Values", "restorePhase8RemoteOptionsValues", "stylePrompt", "suppressPackageBadge", "syncAdvancedControls", "syncBetaPresentation", "syncCapacityMeter", "syncClassicCostBadge", "syncReadOnlyDurationRow", "textRegionGeometry"];
  const added=["creativeTextLabel", "installNodeTypography", "installSemanticSerialization", "installProviderResetMenu", "masterHeightFromRegion", "nodeTypography", "persistMasterPromptHeight", "providerAutoLabel", "providerControlGroups", "providerControlLabel", "providerDisplayValue", "syncProviderGroupHeading", "syncProviderNumericState", "updateProviderIntent"];
  assert.deepEqual(Object.keys(pin.functions).sort(),allowed.sort());assert.deepEqual(Object.keys(pin.added).sort(),added.sort());
  let restored=normalize(current);
  for(const name of allowed){const text=body(restored,name);assert.equal(sha(text),pin.functions[name],name);restored=restored.replace(text,()=>body(before,name));}
  for(const name of added){const text=body(restored,name);assert.equal(sha(text),pin.added[name],name);assert(restored.includes(text+'\n'));restored=restored.replace(text+'\n','');}
  assert.equal(restored.split(pin.registration).length,2);restored=restored.replace(pin.registration,'');
  assert.equal(restored,before,'Protected remainder, registration, globals and all other functions exact');
 }
 return before;
}
