import test from "node:test";
import assert from "node:assert/strict";
import {
    AutoCaptureCountdown,
    CAPTURE_STABILITY_MS,
    isFatalVoiceRecognitionError,
    isCaptureEligible,
    parseVoiceCommand,
    supportsOnDeviceRecognition,
    VoiceCommandGate,
    voiceCaptureAllowed,
    voiceRecognitionErrorMessage
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

test("all six voice commands are recognized exactly", () => {
    const commands = [
        ["Start camera", "start-camera"],
        ["take photo.", "take-photo"],
        ["Retake photo", "retake-photo"],
        ["Capture passport", "capture-passport"],
        ["Stop camera", "stop-camera"],
        ["Repeat instructions", "repeat-instructions"]
    ];
    for (const [phrase, command] of commands) {
        assert.equal(parseVoiceCommand(phrase), command);
    }
    assert.equal(parseVoiceCommand("please take photo now"), null);
    assert.equal(parseVoiceCommand(""), null);
});

test("voice commands require explicit enablement and suppress rapid duplicates", () => {
    const gate = new VoiceCommandGate(1800);
    assert.equal(gate.accept("Start camera", 0), null);
    gate.enable();
    assert.equal(gate.accept("Start camera", 100), "start-camera");
    assert.equal(gate.accept("Start camera", 500), null);
    assert.equal(gate.accept("Start camera", 2000), "start-camera");
    gate.disable();
    assert.equal(gate.accept("Stop camera", 2100), null);
});

test("on-device-only recognition is required and permission errors are explained", () => {
    class LocalSpeechRecognition {}
    LocalSpeechRecognition.prototype.processLocally = false;
    class RemoteOnlySpeechRecognition {}
    assert.equal(supportsOnDeviceRecognition(LocalSpeechRecognition), true);
    assert.equal(supportsOnDeviceRecognition(RemoteOnlySpeechRecognition), false);
    assert.equal(supportsOnDeviceRecognition(undefined), false);
    assert.match(voiceRecognitionErrorMessage("not-allowed"), /permission was denied/i);
    assert.match(voiceRecognitionErrorMessage("language-not-supported"), /on-device language pack/i);
    assert.equal(isFatalVoiceRecognitionError("not-allowed"), true);
    assert.equal(isFatalVoiceRecognitionError("audio-capture"), true);
    assert.equal(isFatalVoiceRecognitionError("no-speech"), false);
});

test("manual or voice capture is ineligible until every capture check passes", () => {
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

test("manual capture and voice requests share the exact same eligibility gate", () => {
    const checks = { ...eligible, stableForMs: CAPTURE_STABILITY_MS - 10 };
    assert.equal(isCaptureEligible(checks), false);
    checks.stableForMs = CAPTURE_STABILITY_MS;
    assert.equal(isCaptureEligible(checks), true);
    checks.captureInProgress = true;
    assert.equal(isCaptureEligible(checks), false);
});

test("voice photo commands never authorize capture when liveness checks are incomplete", () => {
    assert.equal(voiceCaptureAllowed("take-photo", false), false);
    assert.equal(voiceCaptureAllowed("capture-passport", false), false);
    assert.equal(voiceCaptureAllowed("take-photo", true), true);
    assert.equal(voiceCaptureAllowed("repeat-instructions", true), false);
});
