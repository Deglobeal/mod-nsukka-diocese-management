import test from "node:test";
import assert from "node:assert/strict";
import { getFaceMeasurements, LivenessSession, createChallengeSequence } from "../../static/js/registration/passport-liveness.mjs";

const box = { x: 0.3, y: 0.2, width: 0.4, height: 0.5 };
const face = (overrides = {}) => ({
    faceCount: 1,
    positioned: true,
    eyeAspect: 0.3,
    yaw: 0,
    faceBox: box,
    ...overrides
});

function prime(session) {
    let result;
    for (let now = 0; now < 800; now += 100) result = session.step(face(), now);
    return result;
}

test("challenge sequence varies order and turn direction", () => {
    assert.deepEqual(createChallengeSequence(() => 0), ["blink", "turn-left"]);
    assert.deepEqual(createChallengeSequence(() => 0.99), ["turn-right", "blink"]);
});

test("face measurements estimate head roll from the eye line", () => {
    const landmarks = Array.from({ length: 468 }, () => ({ x: 0.5, y: 0.5 }));
    landmarks[33] = { x: 0.4, y: 0.48 };
    landmarks[263] = { x: 0.6, y: 0.52 };
    landmarks[1] = { x: 0.5, y: 0.5 };
    for (const [outerA, innerA, upperA, upperB, lowerB, lowerA] of [
        [33, 160, 158, 133, 153, 144],
        [362, 385, 387, 263, 373, 380]
    ]) {
        landmarks[outerA] = { x: 0.4, y: 0.48 };
        landmarks[innerA] = { x: 0.43, y: 0.48 };
        landmarks[upperA] = { x: 0.45, y: 0.47 };
        landmarks[upperB] = { x: 0.47, y: 0.48 };
        landmarks[lowerB] = { x: 0.46, y: 0.49 };
        landmarks[lowerA] = { x: 0.42, y: 0.49 };
    }
    landmarks[263] = { x: 0.6, y: 0.52 };
    const measurements = getFaceMeasurements(landmarks);
    assert.ok(Math.abs(measurements.roll - Math.atan2(0.04, 0.2)) < 1e-12);
});

test("no face and multiple faces never pass or consume the challenge timeout", () => {
    const session = new LivenessSession({ timeoutMs: 10 });
    assert.equal(session.step(face({ faceCount: 0 }), 0).state, "no-face");
    assert.equal(session.step(face({ faceCount: 2 }), 1).state, "multiple-faces");
    assert.equal(session.step(face(), 1000).state, "position");
    assert.equal(session.complete, false);
});

test("challenge timeout starts when the first liveness challenge begins", () => {
    const session = new LivenessSession({ random: () => 0, timeoutMs: 1000 });
    let result;
    for (let now = 0; now <= 800; now += 100) {
        result = session.step(face(), now);
    }
    assert.equal(result.state, "challenge");
    assert.ok(session.startedAt < 800);
    assert.equal(session.step(face(), session.startedAt + 1001).state, "timeout");
});

test("head-turn challenge keeps sampling intentional motion without requiring a still face box", () => {
    const session = new LivenessSession({ random: () => 0.99 });
    prime(session);
    assert.equal(session.challenge, "turn-right");

    let now = 800;
    for (let i = 0; i < 4; i += 1) {
        session.step(face({
            yaw: 0.12,
            faceBox: { ...box, x: box.x + i * 0.05 }
        }), now);
        now += 100;
    }
    assert.equal(session.turnSeen, true);
    for (let i = 0; i < 3; i += 1) {
        session.step(face({ yaw: 0 }), now);
        now += 100;
    }
    assert.equal(session.challenge, "blink");
});

test("blink needs open, closed and reopened eye observations", () => {
    const session = new LivenessSession({ random: () => 0 });
    prime(session);
    for (let i = 0; i < 3; i += 1) session.step(face(), 800 + i * 100);
    session.step(face({ eyeAspect: 0.15 }), 1100);
    assert.equal(session.complete, false);
    for (let i = 0; i < 3; i += 1) session.step(face(), 1200 + i * 100);
    assert.equal(session.challenge, "turn-left");
});

test("failed blink without reopening cannot pass", () => {
    const session = new LivenessSession({ random: () => 0 });
    prime(session);
    for (let i = 0; i < 8; i += 1) session.step(face({ eyeAspect: 0.15 }), 800 + i * 100);
    assert.equal(session.complete, false);
});

for (const [name, direction] of [["left", -1], ["right", 1]]) {
    test(`${name} turn requires sustained movement and return to forward`, () => {
        const values = name === "left" ? [0, 0.99] : [0.99, 0.99];
        const session = new LivenessSession({ random: () => values.shift() ?? 0.99 });
        prime(session);
        for (let i = 0; i < 4; i += 1) session.step(face({ yaw: direction * 0.12 }), 800 + i * 100);
        assert.equal(session.complete, false);
        for (let i = 0; i < 3; i += 1) session.step(face(), 1200 + i * 100);
        assert.equal(session.challenge, "blink");
    });
}

test("turn without returning forward does not complete the turn challenge", () => {
    const session = new LivenessSession({ random: () => 0.99 });
    prime(session);
    for (let i = 0; i < 8; i += 1) session.step(face({ yaw: 0.12 }), 800 + i * 100);
    assert.equal(session.complete, false);
    assert.equal(session.challenge, "turn-right");
});

test("capture becomes eligible only after both randomized challenges pass", () => {
    const blinkFirst = new LivenessSession({ random: () => 0 });
    prime(blinkFirst);
    for (const [time, eyeAspect] of [
        [800, 0.3], [900, 0.3], [1000, 0.3], [1100, 0.15],
        [1200, 0.3], [1300, 0.3], [1400, 0.3]
    ]) blinkFirst.step(face({ eyeAspect }), time);
    assert.equal(blinkFirst.complete, false);
    blinkFirst.step(face(), 1500);
    for (const time of [1600, 1700, 1800]) blinkFirst.step(face({ yaw: -0.12 }), time);
    for (const time of [1900, 2000, 2100]) blinkFirst.step(face(), time);
    assert.equal(blinkFirst.complete, true);

    const turnFirst = new LivenessSession({ random: () => 0.99 });
    prime(turnFirst);
    for (const time of [800, 900, 1000]) turnFirst.step(face({ yaw: 0.12 }), time);
    for (const time of [1100, 1200, 1300]) turnFirst.step(face(), time);
    assert.equal(turnFirst.complete, false);
    for (const [time, eyeAspect] of [
        [1400, 0.3], [1500, 0.3], [1600, 0.3], [1700, 0.15],
        [1800, 0.3], [1900, 0.3], [2000, 0.3]
    ]) turnFirst.step(face({ eyeAspect }), time);
    assert.equal(turnFirst.complete, true);
});
