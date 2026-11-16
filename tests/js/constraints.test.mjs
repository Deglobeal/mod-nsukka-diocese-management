import test from "node:test";
import assert from "node:assert/strict";
import {
    cameraConstraintFallbacks,
    selectPreferredCameraDevice,
    zoomConstraintTarget
} from "../../static/js/registration/passport-framing.mjs";

test("front and rear getUserMedia fallbacks prefer ideal settings then facing mode", () => {
    for (const facingMode of ["user", "environment"]) {
        const [preferred, loose, facingOnly] = cameraConstraintFallbacks(facingMode);
        assert.deepEqual(preferred.video.facingMode, { ideal: facingMode });
        assert.equal(preferred.video.width.ideal, 720);
        assert.equal(preferred.video.height.ideal, 1280);
        assert.deepEqual(loose.video.facingMode, { ideal: facingMode });
        assert.equal(facingOnly.video.facingMode, facingMode);
        assert.equal(preferred.audio, false);
    }
});

test("camera chooser prefers front wide and rear main while rejecting telephoto and ultra-wide rear lenses", () => {
    const devices = [
        { kind: "videoinput", deviceId: "front-main", label: "Front Camera" },
        { kind: "videoinput", deviceId: "front-wide", label: "Front Ultra Wide Camera" },
        { kind: "videoinput", deviceId: "rear-tele", label: "Back Telephoto Camera" },
        { kind: "videoinput", deviceId: "rear-ultra", label: "Back Ultra Wide Camera" },
        { kind: "videoinput", deviceId: "rear-main", label: "Back Main Camera" }
    ];
    assert.equal(selectPreferredCameraDevice(devices, "user", "front-main").deviceId, "front-wide");
    assert.equal(selectPreferredCameraDevice(devices, "environment", "rear-tele").deviceId, "rear-main");
    assert.equal(selectPreferredCameraDevice(devices, "environment", "rear-main"), null);
});

test("zoom is skipped when unsupported or fixed and clamped to min plus 0.2", () => {
    assert.equal(zoomConstraintTarget({ zoom: { min: 1, max: 4 } }, { zoom: 2 }), 1.2);
    assert.equal(zoomConstraintTarget({ zoom: { min: 1, max: 4 } }, { zoom: 1.1 }), 1.1);
    assert.equal(zoomConstraintTarget({ zoom: { min: 1, max: 1 } }), null);
    assert.equal(zoomConstraintTarget({}), null);
});
