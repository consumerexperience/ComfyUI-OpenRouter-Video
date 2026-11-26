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
export function package02AmendmentBaselineSource(root,path,current){
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
