import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
    coverRect,
    mapRectToCoverFrame,
    passportCanvasRenderPlan
} from "../../static/js/registration/passport-framing.mjs";

const cameraSource = readFileSync(
    new URL("../../static/js/registration/passport-camera.js", import.meta.url), "utf8"
);
const styles = readFileSync(
    new URL("../../static/css/pages/registration.css", import.meta.url), "utf8"
);

test("CSS preview and 720 by 900 canvas use the same 4:5 cover source rectangle", () => {
    const source = { width: 720, height: 1280 };
    const crop = coverRect(source.width, source.height);
    const exportPlan = passportCanvasRenderPlan(source.width, source.height);
    assert.deepEqual(exportPlan.frame, crop);
    assert.equal(exportPlan.width, 720);
    assert.equal(exportPlan.height, 900);
    assert.match(styles, /registration-passport-square video,[\s\S]*?object-fit:\s*cover/);
    assert.match(cameraSource, /mapRectToCoverFrame/);
    assert.match(cameraSource, /context\.drawImage\(\s*video,\s*renderPlan\.frame\.x,\s*renderPlan\.frame\.y,\s*renderPlan\.frame\.width,\s*renderPlan\.frame\.height/);
});

test("normalized landmark box maps to the exact export crop", () => {
    const box = { x: 180, y: 300, width: 240, height: 500 };
    const crop = coverRect(720, 1280);
    const mapped = mapRectToCoverFrame(box, 720, 1280);
    assert.equal(mapped.x, (box.x - crop.x) / crop.width);
    assert.equal(mapped.y, (box.y - crop.y) / crop.height);
    assert.equal(mapped.height, box.height / crop.height);
});
