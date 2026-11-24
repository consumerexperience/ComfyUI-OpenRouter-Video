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
export function package02AmendmentBaselineSource(root,path,current){
 const pin=JSON.parse(readFileSync(new URL('tests/fixtures/package02-amendments-source-candidate.json',root),'utf8'));
 if(!pin.files[path] || sha(current)!==pin.files[path])return current;
 assert.equal(pin.status,'UNACCEPTED_PACKAGE02_FINAL_12');assert.equal(pin.baseline,base);
 const before=normalize(execFileSync('git',['show',`${base}:${path}`],{cwd:root,encoding:'utf8'}));assert.equal(sha(before),pin.baseline_files[path]);
 if(path==='web/openrouter_video.js'){
  const allowed=["restorePhase10NamedValues", "suppressPackageBadge", "installParameterColumns", "textRegionGeometry", "stylePrompt", "orderPresentationWidgets", "applyPresentation", "installResponsiveHeight", "fitPresentationWidth", "installBetaPresentation", "drawCapacityMeter", "syncCapacityMeter", "syncBetaPresentation", "drawReadOnlyValue", "syncReadOnlyDurationRow", "providerObjectIssue", "configureOperationControls", "renderCostDetails", "drawCollapsedCostBadge", "syncClassicCostBadge"];
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
