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
test("automatic duration is selectable only when explicitly advertised", () => {
    const domain=context.durationDomain([-1,4,8]);
    assert.equal(domain.kind,"DISCRETE");
    assert.deepEqual(plain(domain.allowed_values),[-1,4,8]);
    assert.equal(context.durationAtPosition(domain,0),-1);
    assert.equal(context.durationDomain([4,8]).allowed_values.includes(-1),false);
    const range=context.durationDomain({kind:"STEPPED_RANGE",min:1,max:15,step:1});
    assert.equal(context.durationValueAllowed(range,-1),false);
    assert.equal(context.durationValueAllowed(range,4),true);
    assert.equal(context.durationValueAllowed(domain,-1),true);
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

test("mixed Auto keeps one positive slider and a separate reset to the numeric sentinel", () => {
    const values=[];
    const slider = {name:"duration", type:"slider", value:-1, options:{}, __orvDurationAdapter:true,
        callback:value=>values.push(value)};
    const node = {widgets:[{name:"model"},slider,{name:"seed"}],__orvCapabilityStatus:{value:""}};
    context.configureDuration(node,[-1,4,5,6]);
    assert.equal(node.widgets[1],slider);
    assert.equal(slider.type,"slider");
    assert.deepEqual(plain(slider.__orvSliderDomain.allowed_values),[4,5,6]);
    assert.equal(slider.options.min,4);
    assert.equal(slider.options.max,6);
    assert.equal(slider.value,-1);
    slider.value=5;
    slider.__orvResetDuration();
    assert.equal(slider.value,-1);
    assert.deepEqual(values,[-1]);
    context.configureDuration(node,[4,5,6]);
    assert.equal(node.widgets[1],slider);
    assert.equal(slider.__orvResetDuration,undefined);
    assert.equal(slider.value,4);
    assert.deepEqual(node.widgets.map(w=>w.name),["model","duration","seed"]);
    context.configureDuration(node,[]);
    assert.equal(slider.hidden,true);
});
