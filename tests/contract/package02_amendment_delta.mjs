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
export function package02AmendmentBaselineSource(root,path,current){
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
