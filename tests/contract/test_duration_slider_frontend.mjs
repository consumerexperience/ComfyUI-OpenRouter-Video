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
