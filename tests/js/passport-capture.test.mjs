import test from "node:test";
import assert from "node:assert/strict";
import {
    AutoCaptureCountdown,
    CAPTURE_STABILITY_MS,
    isCaptureEligible
} from "../../static/js/registration/passport-capture.mjs";

const eligible = {
    faceCount: 1,
    positioned: true,
    livenessPassed: true,
    facingForward: true,
    glassesCheckPassed: true,
    lightingAdequate: true,
    stableForMs: CAPTURE_STABILITY_MS,
    captureInProgress: false
};

test("capture is ineligible until every check passes", () => {
    assert.equal(isCaptureEligible({ ...eligible, livenessPassed: false }), false);
    assert.equal(isCaptureEligible({ ...eligible, faceCount: 0 }), false);
    assert.equal(isCaptureEligible({ ...eligible, faceCount: 2 }), false);
    assert.equal(isCaptureEligible({ ...eligible, positioned: false }), false);
    assert.equal(isCaptureEligible({ ...eligible, facingForward: false }), false);
    assert.equal(isCaptureEligible({ ...eligible, glassesCheckPassed: false }), false);
    assert.equal(isCaptureEligible({ ...eligible, lightingAdequate: false }), false);
    assert.equal(isCaptureEligible({ ...eligible, stableForMs: CAPTURE_STABILITY_MS - 1 }), false);
    assert.equal(isCaptureEligible({ ...eligible, captureInProgress: true }), false);
    assert.equal(isCaptureEligible(eligible), true);
});

test("automatic countdown waits three seconds and fires only once", () => {
    const countdown = new AutoCaptureCountdown(3000);
    assert.deepEqual(countdown.update(true, true, 1000), { state: "countdown", seconds: 3 });
    assert.deepEqual(countdown.update(true, true, 2000), { state: "countdown", seconds: 2 });
    assert.deepEqual(countdown.update(true, true, 3000), { state: "countdown", seconds: 1 });
    assert.deepEqual(countdown.update(true, true, 4000), { state: "capture", seconds: 0 });
    assert.deepEqual(countdown.update(true, true, 5000), { state: "fired" });
});

test("countdown cancels and resets when eligibility is lost or automatic mode is disabled", () => {
    const countdown = new AutoCaptureCountdown(3000);
    countdown.update(true, true, 0);
    assert.deepEqual(countdown.update(false, true, 1000), { state: "waiting" });
    assert.deepEqual(countdown.update(true, true, 1100), { state: "countdown", seconds: 3 });
    assert.deepEqual(countdown.update(true, false, 1200), { state: "manual" });
    assert.deepEqual(countdown.update(true, true, 1300), { state: "countdown", seconds: 3 });
});

test("countdown restarts after missing face, multiple faces, movement or dark lighting", () => {
    const invalidFrames = [
        { faceCount: 0 },
        { faceCount: 2 },
        { positioned: false },
        { facingForward: false },
        { lightingAdequate: false },
        { stableForMs: 200 }
    ];
    let now = 0;
    for (const invalid of invalidFrames) {
        const countdown = new AutoCaptureCountdown(3000);
        assert.equal(countdown.update(isCaptureEligible(eligible), true, now).state, "countdown");
        assert.equal(countdown.update(isCaptureEligible({ ...eligible, ...invalid }), true, now + 1000).state, "waiting");
        assert.equal(countdown.update(isCaptureEligible(eligible), true, now + 1100).seconds, 3);
        now += 2000;
    }
});

test("manual capture uses the same eligibility gate as automatic capture", () => {
    const checks = { ...eligible, stableForMs: CAPTURE_STABILITY_MS - 10 };
    assert.equal(isCaptureEligible(checks), false);
    checks.stableForMs = CAPTURE_STABILITY_MS;
    assert.equal(isCaptureEligible(checks), true);
    checks.captureInProgress = true;
    assert.equal(isCaptureEligible(checks), false);
});
