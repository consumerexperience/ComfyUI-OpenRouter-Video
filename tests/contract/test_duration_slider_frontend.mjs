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

function minimalSliderFixture(value = 0) {
    const elements = [];
    const document = { createElement(tag) {
        const element = { tag, style: {}, attributes: {}, children: [], events: {},
            setAttribute(name, value) { this.attributes[name] = value; },
            append(...children) { this.children.push(...children); },
            addEventListener(name, callback) { this.events[name] = callback; },
        };
        elements.push(element);
        return element;
    } };
    const scoped = { app: { registerExtension() {} }, api: {}, document };
    vm.runInNewContext(source, scoped);
    const previous = { name: "duration", value };
    let chained = 0;
    const unrelatedMenu = { content: "Existing node action" };
    const node = {
        widgets: [previous], __orvCapabilityStatus: { value: "" },
        getExtraMenuOptions() { chained++; return [unrelatedMenu]; },
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options };
            Object.defineProperty(widget, "value", {
                get: options.getValue,
                set(next) { options.setValue(next); widget.callback?.(next); },
            });
            this.widgets.push(widget);
            return widget;
        },
    };
    scoped.createDurationSlider(node, previous);
    const item = node.widgets[0];
    item.__orvComputeSize = item.computeSize; // applyPresentation caches this in the real node
    const range = elements.find(e => e.type === "range");
    const output = elements.filter(e => e.tag === "span")[1];
    return { scoped, node, item, range, output, elements, chained: () => chained, unrelatedMenu };
}

for (const values of [[5, 10], [4, 6, 8], Array.from({ length: 30 }, (_, i) => i + 1)]) {
    test(`minimal visible surface and drag preserves ${values.length} discrete values`, () => {
        const { scoped, node, item, range, output, elements } = minimalSliderFixture();
        scoped.configureDuration(node, values);
        assert.equal(output.textContent, "Default");
        assert.equal(item.value, 0); // fresh node keeps omission, never selects minimum implicitly
        assert.deepEqual(elements.map(e => e.tag), ["div", "div", "span", "span", "input"]);
        assert.equal(elements.some(e => e.tag === "button" || e.tag === "datalist"), false);
        assert.equal(item.element.children.length, 2); // header + track only, no footer
        assert.ok(item.computeSize()[1] < 70);
        for (let position = 0; position < values.length; position++) {
            range.value = position;
            range.events.input();
            assert.equal(item.value, values[position]);
            assert.equal(output.textContent, `${values[position]}s`);
            assert.equal(item.serializeValue(), values[position]);
        }
        range.value = 0;
        range.events.click();
        assert.equal(item.serializeValue(), values[0]);
    });
}

test("native contextual reset preserves previous node actions and Default omission sentinel", () => {
    const f = minimalSliderFixture(8);
    f.scoped.configureDuration(f.node, [4, 6, 8]);
    const options = f.node.getExtraMenuOptions({}, []);
    assert.equal(f.chained(), 1);
    assert.equal(options[1], f.unrelatedMenu);
    assert.equal(options[0].content, "Reset Duration to model default");
    options[0].callback();
    assert.equal(f.output.textContent, "Default");
    assert.equal(f.item.serializeValue(), 0);
    assert.equal(f.node.__orvCapabilityStatus.value, ""); // no permanent instructional hint
    const restored = minimalSliderFixture(JSON.parse(JSON.stringify(f.item.serializeValue())));
    restored.scoped.configureDuration(restored.node, [4, 6, 8]);
    assert.equal(restored.output.textContent, "Default");
    assert.equal(restored.item.serializeValue(), 0);
});

test("explicit semantic seconds survive save/reload independently of slider index", () => {
    const f = minimalSliderFixture(8);
    f.scoped.configureDuration(f.node, [4, 6, 8]);
    assert.equal(f.range.value, 2);
    const saved = JSON.stringify(f.item.serializeValue());
    assert.equal(saved, "8");
    const restored = minimalSliderFixture(JSON.parse(saved));
    restored.scoped.configureDuration(restored.node, [4, 6, 8]);
    assert.equal(restored.item.value, 8);
    assert.equal(restored.output.textContent, "8s");
    assert.equal(restored.range.value, 2);
});

test("sparse keyboard and model/method reprojection keep the same semantic domain", () => {
    const f = minimalSliderFixture(2);
    const event = key => ({ key, preventDefault() {}, stopPropagation() {} });
    f.scoped.configureDuration(f.node, [1, 2, 5, 10]);
    f.range.events.keydown(event("ArrowRight"));
    assert.equal(f.item.value, 5);
    f.range.events.keydown(event("Home"));
    assert.equal(f.item.value, 1);
    f.range.events.keydown(event("End"));
    assert.equal(f.item.value, 10);
    f.scoped.configureDuration(f.node, [4, 6, 8]); // model change preserves incompatible intent
    assert.equal(f.item.value, 10);
    assert.match(f.node.__orvCapabilityStatus.value, /incompatible/);
    const capability = {
        supported_durations: [4, 6, 8], supported_resolutions: ["720p", "1080p"],
        configuration_relations: [{ axes: ["resolution", "duration"], when: { inference_method: ["I2V"] }, complete: true,
            allowed: [{ resolution: ["1080p"], duration: [4, 6] }, { resolution: ["720p"], duration: [4, 6, 8] }], forbidden: [] }],
    };
    for (const [method, expected] of [["T2V", [4, 6, 8]], ["I2V", [4, 6]]]) {
        const projected = f.scoped.configurationOptions(capability, { resolution: "1080p" }, { inference_method: method });
        f.scoped.configureDuration(f.node, projected.options.duration);
        assert.deepEqual(plain(f.item.__orvDomain.allowed_values), expected);
        assert.equal(f.item.value, 10);
    }
});

test("polish preserves classifier, adaptation, wire, native media and all non-Duration functions", async () => {
    const { execFileSync } = await import("node:child_process");
    const root = new URL("../../", import.meta.url);
    const baseline = execFileSync("git", ["show", "574ed24669e0662976569c87329ec7a0c01b7a88:web/openrouter_video.js"], { cwd: root, encoding: "utf8" });
    const functions = text => Object.fromEntries(text.replace(/\r\n/g, "\n").split(/(?=^function |^async function )/m).slice(1).map(part => [part.match(/function (\w+)/)[1], part.slice(0, part.lastIndexOf("}") + 1).trim()]));
    const before = functions(baseline), after = functions(source);
    for (const name of Object.keys(before)) if (!["createDurationSlider", "configureDuration"].includes(name)) assert.equal(after[name], before[name], name);
});
