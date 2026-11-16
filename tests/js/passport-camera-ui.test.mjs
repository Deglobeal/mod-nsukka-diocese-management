import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const cameraScript = readFileSync(
    new URL("../../static/js/registration/passport-camera.js", import.meta.url),
    "utf8"
);
const cameraTemplate = readFileSync(
    new URL("../../templates/registration/registration.html", import.meta.url),
    "utf8"
);
const registrationStyles = readFileSync(
    new URL("../../static/css/pages/registration.css", import.meta.url),
    "utf8"
);

test("passport capture has no voice recognition or speech output controls", () => {
    assert.doesNotMatch(cameraScript, /SpeechRecognition|speechSynthesis|SpeechSynthesisUtterance/);
    assert.doesNotMatch(cameraTemplate, /passport-voice|voice commands|microphone/i);
    assert.doesNotMatch(cameraScript, /passport-voice|voice commands|microphone/i);
});

test("mobile capture stage handles safe areas and both screen orientations", () => {
    assert.match(registrationStyles, /passport-camera-stage-open[\s\S]*?100dvh/);
    assert.match(registrationStyles, /safe-area-inset-top/);
    assert.match(registrationStyles, /safe-area-inset-bottom/);
    assert.match(registrationStyles, /orientation:\s*landscape/);
    assert.match(registrationStyles, /overflow-x:\s*hidden/);
});

test("front camera preview mirrors visually while capture stays sourced from video", () => {
    assert.match(registrationStyles, /passport-camera-video-mirrored\s*\{\s*transform:\s*scaleX\(-1\)/);
    assert.match(cameraScript, /context\.drawImage\(\s*video,/);
    assert.match(cameraScript, /mirrorRectHorizontally/);
});
