import test from "node:test";
import assert from "node:assert/strict";
import {
    containRect,
    cameraConstraintFallbacks,
    getPassportFaceGuidance,
    mapRectToContainFrame,
    mirrorRectHorizontally,
    minimumSupportedZoom,
    nextFacingMode,
    passportCanvasRenderPlan,
    selectWideCameraDevice,
    PASSPORT_FRAME_HEIGHT,
    PASSPORT_FRAME_WIDTH,
    stopMediaTracks
} from "../../static/js/registration/passport-framing.mjs";

test("portrait and landscape sources fit fully inside the 4:5 frame", () => {
    const portrait = containRect(720, 1280);
    assert.equal(portrait.width, 506.25);
    assert.equal(portrait.height, PASSPORT_FRAME_HEIGHT);
    assert.equal(portrait.x, 106.875);

    const landscape = containRect(1920, 1080);
    assert.equal(landscape.width, PASSPORT_FRAME_WIDTH);
    assert.equal(landscape.height, 405);
    assert.equal(landscape.y, 247.5);
});

test("capture uses a fixed 4:5 canvas and contains the full source frame", () => {
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
    assert.ok(Math.abs(mapped.x - (fit.x + sourceRect.x * fit.scale) / PASSPORT_FRAME_WIDTH) < 1e-12);
    assert.ok(Math.abs(mapped.y - (fit.y + sourceRect.y * fit.scale) / PASSPORT_FRAME_HEIGHT) < 1e-12);
    assert.equal(mapped.width, sourceRect.width * fit.scale / PASSPORT_FRAME_WIDTH);
});

test("selfie preview mirrors face guidance without changing the source capture", () => {
    const sourceFace = { x: 80, y: 200, width: 180, height: 240 };
    const mirroredFace = mirrorRectHorizontally(sourceFace, 720);
    assert.deepEqual(mirroredFace, { x: 460, y: 200, width: 180, height: 240 });
    assert.equal(sourceFace.x, 80);
});

test("normalized framing guidance handles distance, alignment and ready position", () => {
    assert.equal(getPassportFaceGuidance(null), "no-face");
    assert.equal(getPassportFaceGuidance({ x: 0.43, y: 0.2, width: 0.10, height: 0.15 }), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.1, width: 0.45, height: 0.5 }), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.42, y: 0.2, width: 0.2, height: 0.25 }, 0.25), "straight");
    assert.equal(getPassportFaceGuidance({ x: 0.05, y: 0.2, width: 0.2, height: 0.25 }), "right");
    assert.equal(getPassportFaceGuidance({ x: 0.42, y: 0.2, width: 0.2, height: 0.25 }), "ready");
});

test("distance guidance uses hysteresis to avoid flicker near thresholds", () => {
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.2, width: 0.44, height: 0.25 }), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.2, width: 0.40, height: 0.25 }, 0, "farther"), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.2, width: 0.37, height: 0.25 }, 0, "farther"), "ready");
    assert.equal(getPassportFaceGuidance({ x: 0.4, y: 0.2, width: 0.13, height: 0.16 }), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.4, y: 0.2, width: 0.16, height: 0.19 }, 0, "closer"), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.4, y: 0.2, width: 0.19, height: 0.23 }, 0, "closer"), "ready");
});

test("camera switch alternates rear and front preference", () => {
    assert.equal(nextFacingMode("environment"), "user");
    assert.equal(nextFacingMode("user"), "environment");
});

test("camera constraints use non-exact preferences and include broad fallbacks", () => {
    const [preferred, facingOnly, generic] = cameraConstraintFallbacks("environment");
    assert.deepEqual(preferred.video.facingMode, { ideal: "environment" });
    assert.equal(preferred.audio, false);
    assert.equal(preferred.video.width.ideal, 720);
    assert.equal(preferred.video.height.ideal, 1280);
    assert.equal(preferred.video.aspectRatio.ideal, 9 / 16);
    assert.deepEqual(facingOnly.video.facingMode, { ideal: "environment" });
    assert.equal(generic.video, true);
});

test("camera selection prefers explicitly labelled wide cameras for each direction", () => {
    const devices = [
        { kind: "videoinput", deviceId: "front", label: "Front Camera" },
        { kind: "videoinput", deviceId: "front-wide", label: "Front Ultra Wide Camera" },
        { kind: "videoinput", deviceId: "rear-tele", label: "Back Telephoto Camera" },
        { kind: "videoinput", deviceId: "rear-wide", label: "Back Wide Angle Camera" }
    ];
    assert.equal(selectWideCameraDevice(devices, "user", "front")?.deviceId, "front-wide");
    assert.equal(selectWideCameraDevice(devices, "environment", "rear-tele")?.deviceId, "rear-wide");
    assert.equal(selectWideCameraDevice([
        { kind: "videoinput", deviceId: "rear-tele", label: "Back Telephoto Camera" },
        { kind: "videoinput", deviceId: "rear-main", label: "Back Camera" }
    ], "environment", "rear-tele")?.deviceId, "rear-main");
    assert.equal(selectWideCameraDevice(devices.slice(0, 1), "user", "front"), null);
});

test("zoom fallback uses the minimum only when valid capability bounds are reported", () => {
    assert.equal(minimumSupportedZoom({ zoom: { min: 1, max: 4 } }), 1);
    assert.equal(minimumSupportedZoom({ zoom: { min: 2, max: 2 } }), 2);
    assert.equal(minimumSupportedZoom({}), null);
    assert.equal(minimumSupportedZoom({ zoom: { min: 4, max: 2 } }), null);
});

test("camera cleanup stops each active media track", () => {
    let stopped = 0;
    stopMediaTracks({
        getTracks: () => [{ stop: () => stopped += 1 }, { stop: () => stopped += 1 }]
    });
    assert.equal(stopped, 2);
});
