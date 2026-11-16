import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { nextFacingMode, stopMediaTracks } from "../../static/js/registration/passport-framing.mjs";

const cameraSource = readFileSync(
    new URL("../../static/js/registration/passport-camera.js", import.meta.url), "utf8"
);

test("switch stops the old stream, changes facing preference, and preserves the liveness session", () => {
    let stopped = 0;
    stopMediaTracks({ getTracks: () => [{ stop: () => { stopped += 1; } }] });
    assert.equal(stopped, 1);
    assert.equal(nextFacingMode("user"), "environment");
    assert.equal(nextFacingMode("environment"), "user");
    assert.match(cameraSource, /preserveLivenessOnNextCameraStart = true;[\s\S]*?requestedFacingMode = nextFacingMode\(requestedFacingMode\);[\s\S]*?startCamera\(\)/);
    assert.match(cameraSource, /if \(!preserveLiveness\)\s*\{\s*livenessSession = new LivenessSession/);
    assert.match(cameraSource, /updateCameraIndicator\(/);
});
