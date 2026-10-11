import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
const source = readFileSync(new URL("../../web/openrouter_video.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/gm, "");
const context = { app: { registerExtension() {} }, api: {} };
vm.runInNewContext(source, context);
const plain = value => JSON.parse(JSON.stringify(value));
for (const values of [[5,10], [4,6,8], [1,2,3,4,5,10], Array.from({length:30}, (_,i)=>i+1)]) {
    test(`discrete domain and snapping ${values.length} values`, () => {
        const domain = context.durationDomain(values);
        assert.equal(domain.kind, "DISCRETE");
        assert.deepEqual(plain(domain.allowed_values), values);
        for (let i=-1;i<=values.length;i+=0.1) assert.ok(values.includes(context.durationAtPosition(domain,i)));
    });
}
test("unknown and unconfirmed range fail closed", () => {
    for (const value of [null, [], {min:1,max:30}, {kind:"CONTINUOUS_RANGE",min:1,max:30}, [0,4]]) {
        assert.equal(context.durationDomain(value).kind,"UNKNOWN");
    }
});
test("future explicitly confirmed range fixtures remain UI architecture only", () => {
    const stepped=context.durationDomain({kind:"STEPPED_RANGE",min:1,max:30,step:1});
    assert.equal(stepped.kind,"STEPPED_RANGE");
    assert.equal(stepped.allowed_values.length,30);
    const continuous=context.durationDomain({kind:"CONTINUOUS_RANGE",continuous:true,min:1,max:30,precision:1});
    assert.equal(context.durationAtPosition(continuous,7.5),7.5);
    assert.equal(context.durationAtPosition(continuous,31),30);
    assert.equal(context.durationDomain(Array.from({length:30},(_,i)=>i+1)).kind,"DISCRETE");
});
test("model/method/coupled reprojection preserves saved intent and unrelated values", () => {
    const duration={name:"duration",value:8,options:{}};
    const resolution={name:"resolution",value:"720p"};
    const target={widgets:[duration,resolution],__orvCapabilityStatus:{value:""}};
    context.configureDuration(target,[4,6,8]);
    const saved=JSON.stringify(target.widgets.map(w=>w.value));
    context.configureDuration(target,[5,10]);
    assert.equal(duration.value,8);
    assert.match(target.__orvCapabilityStatus.value,/incompatible/);
    assert.equal(JSON.stringify(target.widgets.map(w=>w.value)),saved);
    duration.value=JSON.parse(saved)[0];
    context.configureDuration(target,[4,6,8]);
    assert.equal(duration.value,8);
    duration.value=0;
    context.configureDuration(target,[5,10]);
    assert.equal(duration.value,0);
    assert.equal(duration.options.getOptionLabel(0),"AUTO / MODEL DEFAULT");
    assert.equal(resolution.value,"720p");
});
test("protected frontend definitions remain byte-equivalent to accepted baseline", async () => {
    const {execFileSync}=await import("node:child_process");
    const root=new URL("../../",import.meta.url);
    const baseline=execFileSync("git",["show","8ec71ba94575f8b02105a0cd0e5feba7d7083b87:web/openrouter_video.js"],{cwd:root,encoding:"utf8"});
    const functions=text=>Object.fromEntries(text.replace(/\r\n/g,"\n").split(/(?=^function |^async function )/m).slice(1).map(part=>[part.match(/function (\w+)/)[1],part.slice(0,part.lastIndexOf("}")+1).trim()]));
    const before=functions(baseline), after=functions(readFileSync(new URL("../../web/openrouter_video.js",import.meta.url),"utf8"));
    for(const name of Object.keys(before)) if(!["createGeometryCombos","configureDuration"].includes(name)) assert.equal(after[name],before[name],name);
});

test("native DOM setter preserves semantic seconds without INT callback recursion", () => {
    const elements=[];
    const element=()=>{const e={style:{},events:{},setAttribute(){},append(){},replaceChildren(){},addEventListener(name,handler){this.events[name]=handler;}};elements.push(e);return e;};
    const domContext={app:{registerExtension(){}},api:{},document:{createElement:element}};
    vm.runInNewContext(source,domContext);
    const previous={name:"duration",value:10,callback(next){this.value=next;}};
    const node={widgets:[previous],addDOMWidget(name,type,element,options){
        const item={name,type,options};
        Object.defineProperty(item,"value",{get:options.getValue,set(next){options.setValue(next);item.callback?.(next);}});
        this.widgets.push(item);return item;
    }};
    domContext.createDurationSlider(node,previous);
    const item=node.widgets[0];
    assert.equal(item.callback,null);
    item.value=10;
    assert.equal(item.serializeValue(),10);
    item.value=0;
    assert.equal(item.serializeValue(),0);
    domContext.configureDuration(node,[4]);
    const range=elements.find(e=>e.type==="range");
    range.events.click();
    assert.equal(item.serializeValue(),4);
});
