import test from "node:test";
import assert from "node:assert/strict";
import {
    containRect,
    cameraConstraintFallbacks,
    getPassportFaceGuidance,
    mapRectToContainFrame,
    nextFacingMode,
    passportCanvasRenderPlan,
    PASSPORT_FRAME_HEIGHT,
    PASSPORT_FRAME_WIDTH
} from "../../static/js/registration/passport-framing.mjs";

test("portrait and landscape sources fit without cropping or distortion", () => {
    const portrait = containRect(720, 1280);
    assert.equal(portrait.height, PASSPORT_FRAME_HEIGHT);
    assert.ok(portrait.width < PASSPORT_FRAME_WIDTH);
    assert.equal(portrait.x, (PASSPORT_FRAME_WIDTH - portrait.width) / 2);

    const landscape = containRect(1920, 1080);
    assert.equal(landscape.width, PASSPORT_FRAME_WIDTH);
    assert.ok(landscape.height < PASSPORT_FRAME_HEIGHT);
    assert.equal(landscape.y, (PASSPORT_FRAME_HEIGHT - landscape.height) / 2);
});

test("capture uses a fixed 4:5 canvas and the same contain transform", () => {
    const plan = passportCanvasRenderPlan(1280, 720);
    assert.equal(plan.width, 720);
    assert.equal(plan.height, 900);
    assert.equal(plan.frame.width, 720);
    assert.equal(plan.frame.height, 405);
    assert.equal(plan.frame.y, 247.5);
});

test("face coordinates map to the same centered contain transform as canvas rendering", () => {
    const sourceRect = { x: 180, y: 250, width: 250, height: 360 };
    const mapped = mapRectToContainFrame(sourceRect, 720, 1280);
    const fit = containRect(720, 1280);
    assert.ok(Math.abs(mapped.x - (fit.x + sourceRect.x * fit.scale) / 720) < 1e-12);
    assert.ok(Math.abs(mapped.y - (sourceRect.y * fit.scale) / 900) < 1e-12);
    assert.ok(mapped.width < sourceRect.width / 720);
});

test("normalized framing guidance handles distance, alignment and ready position", () => {
    assert.equal(getPassportFaceGuidance(null), "no-face");
    assert.equal(getPassportFaceGuidance({ x: 0.43, y: 0.2, width: 0.10, height: 0.15 }), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.1, width: 0.45, height: 0.5 }), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.05, y: 0.2, width: 0.2, height: 0.25 }), "right");
    assert.equal(getPassportFaceGuidance({ x: 0.42, y: 0.2, width: 0.2, height: 0.25 }), "ready");
});

test("camera switch alternates rear and front preference", () => {
    assert.equal(nextFacingMode("environment"), "user");
    assert.equal(nextFacingMode("user"), "environment");
});

test("camera constraints use non-exact preferences and include broad fallbacks", () => {
    const [preferred, facingOnly, generic] = cameraConstraintFallbacks("environment");
    assert.deepEqual(preferred.video.facingMode, { ideal: "environment" });
    assert.equal(preferred.video.width.ideal, 720);
    assert.equal(preferred.video.height.ideal, 1280);
    assert.deepEqual(facingOnly.video.facingMode, { ideal: "environment" });
    assert.equal(generic.video, true);
});
