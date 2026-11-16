import test from "node:test";
import assert from "node:assert/strict";
import { getPassportFaceGuidance } from "../../static/js/registration/passport-framing.mjs";

const centeredFace = (height) => ({ x: 0.35, y: (1 - height) / 2, width: 0.3, height });

test("normalized face-height band accepts 30 to 55 percent", () => {
    assert.equal(getPassportFaceGuidance(centeredFace(0.30)), "ready");
    assert.equal(getPassportFaceGuidance(centeredFace(0.42)), "ready");
    assert.equal(getPassportFaceGuidance(centeredFace(0.55)), "ready");
});

test("too-close and too-far states enter and exit with the specified hysteresis", () => {
    assert.equal(getPassportFaceGuidance(centeredFace(0.56)), "farther");
    assert.equal(getPassportFaceGuidance(centeredFace(0.52), 0, "farther"), "farther");
    assert.equal(getPassportFaceGuidance(centeredFace(0.49), 0, "farther"), "ready");
    assert.equal(getPassportFaceGuidance(centeredFace(0.29)), "closer");
    assert.equal(getPassportFaceGuidance(centeredFace(0.33), 0, "closer"), "closer");
    assert.equal(getPassportFaceGuidance(centeredFace(0.36), 0, "closer"), "ready");
});
