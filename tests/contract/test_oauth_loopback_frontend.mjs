import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {execFileSync} from "node:child_process";
import test from "node:test";
const root=new URL("../../",import.meta.url);
test("callback transport repair preserves exact visual and node source",()=>{
 const baseline=execFileSync("git",["show","5b7c524:web/openrouter_video.js"],{cwd:root,encoding:"utf8"}).replace(/\r\n/g,"\n");
 const source=readFileSync(new URL("web/openrouter_video.js",root),"utf8").replace(/\r\n/g,"\n");
 assert.equal(source,baseline.replace('body: JSON.stringify({ callback_url: `${window.location.origin}/openrouter-video/v1/auth/callback` }),','body: JSON.stringify({}),'));
});
