import test from "node:test";
import assert from "node:assert/strict";
import {
    coverRect,
    cameraConstraintFallbacks,
    getPassportFaceGuidance,
    mapRectToCoverFrame,
    mirrorRectHorizontally,
    nextFacingMode,
    passportCanvasRenderPlan,
    selectPreferredCameraDevice,
    zoomConstraintTarget,
    PASSPORT_FRAME_HEIGHT,
    PASSPORT_FRAME_WIDTH,
    stopMediaTracks
} from "../../static/js/registration/passport-framing.mjs";

test("portrait and landscape sources crop to fill the 4:5 frame", () => {
    const portrait = coverRect(720, 1280);
    assert.equal(portrait.width, 720);
    assert.equal(portrait.height, 900);
    assert.equal(portrait.y, 190);

    const landscape = coverRect(1920, 1080);
    assert.equal(landscape.width, 864);
    assert.equal(landscape.height, 1080);
    assert.equal(landscape.x, 528);
});

test("capture uses a fixed 4:5 canvas and the cover crop", () => {
    const plan = passportCanvasRenderPlan(1280, 720);
    assert.equal(plan.width, 720);
    assert.equal(plan.height, 900);
    assert.equal(plan.frame.width, 576);
    assert.equal(plan.frame.height, 720);
    assert.equal(plan.frame.x, 352);
});

test("face coordinates map to the same centered crop as canvas rendering", () => {
    const sourceRect = { x: 180, y: 250, width: 250, height: 360 };
    const mapped = mapRectToCoverFrame(sourceRect, 720, 1280);
    const crop = coverRect(720, 1280);
    assert.ok(Math.abs(mapped.x - (sourceRect.x - crop.x) / crop.width) < 1e-12);
    assert.ok(Math.abs(mapped.y - (sourceRect.y - crop.y) / crop.height) < 1e-12);
    assert.equal(mapped.width, sourceRect.width / crop.width);
});

test("selfie preview mirrors face guidance without changing the source capture", () => {
    const sourceFace = { x: 80, y: 200, width: 180, height: 240 };
    const mirroredFace = mirrorRectHorizontally(sourceFace, 720);
    assert.deepEqual(mirroredFace, { x: 460, y: 200, width: 180, height: 240 });
    assert.equal(sourceFace.x, 80);
});

test("normalized framing guidance handles distance, alignment and ready position", () => {
    assert.equal(getPassportFaceGuidance(null), "no-face");
    assert.equal(getPassportFaceGuidance({ x: 0.43, y: 0.2, width: 0.10, height: 0.29 }), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.1, width: 0.45, height: 0.56 }), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.42, y: 0.3, width: 0.2, height: 0.4 }, 0.25), "straight");
    assert.equal(getPassportFaceGuidance({ x: 0.05, y: 0.3, width: 0.2, height: 0.4 }), "right");
    assert.equal(getPassportFaceGuidance({ x: 0.42, y: 0.3, width: 0.2, height: 0.4 }), "ready");
});

test("distance guidance uses hysteresis to avoid flicker near thresholds", () => {
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.2, width: 0.44, height: 0.56 }), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.2, width: 0.40, height: 0.52 }, 0, "farther"), "farther");
    assert.equal(getPassportFaceGuidance({ x: 0.3, y: 0.25, width: 0.37, height: 0.49 }, 0, "farther"), "ready");
    assert.equal(getPassportFaceGuidance({ x: 0.4, y: 0.35, width: 0.13, height: 0.29 }), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.4, y: 0.33, width: 0.16, height: 0.33 }, 0, "closer"), "closer");
    assert.equal(getPassportFaceGuidance({ x: 0.4, y: 0.32, width: 0.19, height: 0.36 }, 0, "closer"), "ready");
});

test("camera switch alternates rear and front preference", () => {
    assert.equal(nextFacingMode("environment"), "user");
    assert.equal(nextFacingMode("user"), "environment");
});

test("camera constraints use non-exact preferences and include broad fallbacks", () => {
    const [preferred, loose, facingOnly] = cameraConstraintFallbacks("environment");
    assert.deepEqual(preferred.video.facingMode, { ideal: "environment" });
    assert.equal(preferred.audio, false);
    assert.equal(preferred.video.width.ideal, 720);
    assert.equal(preferred.video.height.ideal, 900);
    assert.equal(preferred.video.aspectRatio.ideal, 4 / 5);
    assert.deepEqual(loose.video.facingMode, { ideal: "environment" });
    assert.deepEqual(loose.video.width, { ideal: 640 });
    assert.deepEqual(facingOnly.video, { facingMode: "environment" });
});

test("camera selection prefers front wide and rear primary while rejecting secondary lenses", () => {
    const devices = [
        { kind: "videoinput", deviceId: "front", label: "Front Camera" },
        { kind: "videoinput", deviceId: "front-wide", label: "Front Ultra Wide Camera" },
        { kind: "videoinput", deviceId: "rear-tele", label: "Back Telephoto Camera" },
        { kind: "videoinput", deviceId: "rear-main", label: "Back Main Camera" },
        { kind: "videoinput", deviceId: "rear-wide", label: "Back Ultra Wide Camera" }
    ];
    assert.equal(selectPreferredCameraDevice(devices, "user", "front")?.deviceId, "front-wide");
    assert.equal(selectPreferredCameraDevice(devices, "environment", "rear-wide")?.deviceId, "rear-main");
    assert.equal(selectPreferredCameraDevice([
        { kind: "videoinput", deviceId: "rear-tele", label: "Back Telephoto Camera" },
        { kind: "videoinput", deviceId: "rear-main", label: "Back Camera" }
    ], "environment", "rear-tele")?.deviceId, "rear-main");
    assert.equal(selectPreferredCameraDevice(devices.slice(0, 1), "user", "front"), null);
});

test("zoom constraint uses only device minimum and skips fixed, unsupported, or already-minimum zoom", () => {
    assert.equal(zoomConstraintTarget({ zoom: { min: 1, max: 4 } }, { zoom: 1.8 }), 1);
    assert.equal(zoomConstraintTarget({ zoom: { min: 1, max: 4 } }, { zoom: 1.1 }), 1);
    assert.equal(zoomConstraintTarget({ zoom: { min: 1, max: 4 } }, { zoom: 1 }), null);
    assert.equal(zoomConstraintTarget({ zoom: { min: 2, max: 2 } }), null);
    assert.equal(zoomConstraintTarget({}), null);
});

test("camera cleanup stops each active media track", () => {
    let stopped = 0;
    stopMediaTracks({
        getTracks: () => [{ stop: () => stopped += 1 }, { stop: () => stopped += 1 }]
    });
    assert.equal(stopped, 2);
});
