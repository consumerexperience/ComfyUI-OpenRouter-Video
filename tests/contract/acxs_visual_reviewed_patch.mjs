import {package02BaselineSource} from "./package02_source_delta.mjs";
// Exact UNACCEPTED Owner visual delta. Historical shields keep their original
// assertions; current behavior, raw hashes and protected remainder are tested too.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const base='bd680c1ae2fdd86651162a744a4ecb42d350735b';
const normalized=t=>t.replace(/\r\n/g,'\n');
const sha=t=>createHash('sha256').update(normalized(t)).digest('hex');
export function visualBaselineSource(root,path,current) {
 current=package02BaselineSource(root,path,current);
 const pin=JSON.parse(readFileSync(new URL('tests/fixtures/acxs_visual_source_candidate.json',root),'utf8'));
 if (!pin.files[path] || sha(current)!==pin.files[path]) return current;
 assert.equal(pin.baseline,base);assert.equal(pin.status,'UNACCEPTED_OWNER_VISUAL_DELTA');
 const before=normalized(execFileSync('git',['show',`${base}:${path}`],{cwd:root,encoding:'utf8'}));
 assert.equal(sha(before),pin.baseline_files[path]);
 if(path==='web/openrouter_video.js') {
  const body=(s,n)=>{const m=[...s.matchAll(new RegExp(`^(?:async )?function ${n}\\([^\\n]*\\) \\{[\\s\\S]*?^\\}\\n`,'gm'))];assert.equal(m.length,1,n);return m[0][0];};
  let restored=normalized(current);
  const allowed=['sizePrimaryControls','stylePrompt','orderPresentationWidgets','installResponsiveHeight','fitPresentationWidth','syncBetaPresentation','durationPresentationLabel','createDurationSlider','configureOperationControls','reprojectNodeSemantics','projectProviderCostControls'];
  assert.deepEqual(Object.keys(pin.replacements).sort(),allowed.sort());
  for(const name of allowed){const value=body(restored,name);assert.equal(sha(value),pin.replacements[name]);restored=restored.replace(value,()=>body(before,name));}
  const added=['creativeTextWidgets','textRegionGeometry','nativeFlowHeight','readOnlyValueParts','drawReadOnlyValue','syncReadOnlyDurationRow'];
  assert.deepEqual(Object.keys(pin.added).sort(),added.sort());
  for(const name of added){const value=body(restored,name);assert.equal(sha(value),pin.added[name]);restored=restored.replace(value+'\n','');}
  const registration='            for (const item of this.widgets || []) if (item.name?.startsWith("provider_option:")) setVisible(item,false);\n';
  assert.equal(restored.split(registration).length,2);restored=restored.replace(registration,'');
  const factoryImport='import { ComfyWidgets } from "../../scripts/widgets.js";\n';
  assert.equal(restored.split(factoryImport).length,2);restored=restored.replace(factoryImport,'');
  assert.equal(restored,before,'Only declared creative controls/layout and duration presentation; all other bytes exact');
 }
 return before;
}

export function visualBackendPaths(root) {
 const pin=JSON.parse(readFileSync(new URL('tests/fixtures/acxs_visual_source_candidate.json',root),'utf8'));
 const paths=Object.keys(pin.files).filter(p=>p.startsWith('src/'));
 assert.deepEqual(paths.sort(),['src/openrouter_video/comfy/nodes.py','src/openrouter_video/configuration.py','src/openrouter_video/data/capability-evidence.json']);
 for(const path of paths){const text=readFileSync(new URL(path,root),'utf8');assert.notEqual(visualBaselineSource(root,path,text),text,'Exact explicit backend declaration');}
 return paths;
}
