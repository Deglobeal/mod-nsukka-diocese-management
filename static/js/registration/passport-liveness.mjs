const OPEN_EAR = 0.24;
const CLOSED_EAR = 0.19;
const TURN_THRESHOLD = 0.075;
const RETURN_THRESHOLD = 0.035;
const REQUIRED_STABLE_FRAMES = 3;
export const FORWARD_YAW_TOLERANCE = RETURN_THRESHOLD;

export function isForwardFacing(yaw, baselineYaw) {
    return Number.isFinite(yaw) && Number.isFinite(baselineYaw) &&
        Math.abs(yaw - baselineYaw) <= FORWARD_YAW_TOLERANCE;
}

export function createChallengeSequence(random = Math.random) {
    const turn = random() < 0.5 ? "left" : "right";
    return random() < 0.5
        ? ["blink", `turn-${turn}`]
        : [`turn-${turn}`, "blink"];
}

export function eyeAspectRatio(landmarks, points) {
    if (!landmarks || points.some((index) => !landmarks[index])) return null;
    const distance = (a, b) => Math.hypot(
        landmarks[a].x - landmarks[b].x,
        landmarks[a].y - landmarks[b].y
    );
    const horizontal = distance(points[0], points[3]);
    if (!horizontal) return null;
    return (distance(points[1], points[5]) + distance(points[2], points[4])) /
        (2 * horizontal);
}

export function getFaceMeasurements(landmarks) {
    if (!landmarks || landmarks.length < 264) return null;
    const leftEye = eyeAspectRatio(landmarks, [33, 160, 158, 133, 153, 144]);
    const rightEye = eyeAspectRatio(landmarks, [362, 385, 387, 263, 373, 380]);
    const nose = landmarks[1];
    const eyeMidpoint = (landmarks[33].x + landmarks[263].x) / 2;
    const eyeWidth = Math.abs(landmarks[33].x - landmarks[263].x);
    let eyeDeltaX = landmarks[263].x - landmarks[33].x;
    let eyeDeltaY = landmarks[263].y - landmarks[33].y;
    if (eyeDeltaX < 0) {
        eyeDeltaX *= -1;
        eyeDeltaY *= -1;
    }
    const xs = landmarks.map((point) => point.x);
    const ys = landmarks.map((point) => point.y);
    return {
        eyeAspect: leftEye === null || rightEye === null
            ? null
            : (leftEye + rightEye) / 2,
        yaw: eyeWidth ? (nose.x - eyeMidpoint) / eyeWidth : null,
        roll: eyeWidth ? Math.atan2(eyeDeltaY, eyeDeltaX) : null,
        bounds: {
            left: Math.min(...xs), right: Math.max(...xs),
            top: Math.min(...ys), bottom: Math.max(...ys)
        }
    };
}

export class LivenessSession {
    constructor({ random = Math.random, timeoutMs = 30000 } = {}) {
        this.sequence = createChallengeSequence(random);
        this.index = 0;
        this.startedAt = null;
        this.timeoutMs = timeoutMs;
        this.forwardYaw = null;
        this.openFrames = 0;
        this.closedFrames = 0;
        this.closedAt = null;
        this.reopenFrames = 0;
        this.turnFrames = 0;
        this.returnFrames = 0;
        this.turnSeen = false;
        this.faceStableFrames = 0;
        this.lastFaceBox = null;
        this.state = "position";
    }

    get complete() {
        return this.state === "complete";
    }

    get challenge() {
        return this.sequence[this.index] || null;
    }

    resetChallengeCounters() {
        this.openFrames = 0;
        this.closedFrames = 0;
        this.closedAt = null;
        this.reopenFrames = 0;
        this.turnFrames = 0;
        this.returnFrames = 0;
        this.turnSeen = false;
    }

    step({ faceCount, positioned, eyeAspect, yaw, faceBox }, now) {
        if (this.complete) return { state: "complete" };
        if (this.startedAt === null) this.startedAt = now;
        if (now - this.startedAt > this.timeoutMs) {
            this.state = "timeout";
            return { state: this.state };
        }
        if (faceCount !== 1) {
            this.faceStableFrames = 0;
            this.lastFaceBox = null;
            this.resetChallengeCounters();
            this.forwardYaw = null;
            return { state: faceCount > 1 ? "multiple-faces" : "no-face" };
        }
        if (!positioned || !Number.isFinite(yaw)) {
            this.faceStableFrames = 0;
            this.lastFaceBox = null;
            this.resetChallengeCounters();
            this.forwardYaw = null;
            return { state: "position" };
        }

        const stable = this.lastFaceBox && faceBox &&
            Math.abs(faceBox.x - this.lastFaceBox.x) < 0.025 &&
            Math.abs(faceBox.y - this.lastFaceBox.y) < 0.025 &&
            Math.abs(faceBox.width - this.lastFaceBox.width) < 0.04 &&
            Math.abs(faceBox.height - this.lastFaceBox.height) < 0.04;
        this.lastFaceBox = faceBox;
        this.faceStableFrames = stable ? this.faceStableFrames + 1 : 0;
        if (this.faceStableFrames < REQUIRED_STABLE_FRAMES) {
            return { state: "position" };
        }

        if (this.state === "position") {
            this.state = "challenge";
            this.forwardYaw = yaw;
            return { state: "challenge", challenge: this.challenge, step: this.index + 1, total: this.sequence.length };
        }
        if (this.forwardYaw === null) this.forwardYaw = yaw;

        if (this.challenge === "blink") {
            if (eyeAspect !== null && eyeAspect >= OPEN_EAR) this.openFrames += 1;
            if (this.openFrames >= REQUIRED_STABLE_FRAMES && eyeAspect !== null && eyeAspect <= CLOSED_EAR) {
                this.closedFrames += 1;
                this.closedAt = now;
            }
            if (this.closedFrames >= 1 && eyeAspect !== null && eyeAspect >= OPEN_EAR && now - this.closedAt >= 80) {
                this.reopenFrames += 1;
            }
            if (this.reopenFrames >= REQUIRED_STABLE_FRAMES) this.advance();
        } else {
            const direction = this.challenge === "turn-left" ? -1 : 1;
            const delta = (yaw - this.forwardYaw) * direction;
            if (!this.turnSeen && delta >= TURN_THRESHOLD) this.turnFrames += 1;
            else if (!this.turnSeen) this.turnFrames = 0;
            if (this.turnFrames >= REQUIRED_STABLE_FRAMES) this.turnSeen = true;
            if (this.turnSeen && Math.abs(yaw - this.forwardYaw) <= RETURN_THRESHOLD) {
                this.returnFrames += 1;
            } else if (this.turnSeen) this.returnFrames = 0;
            if (this.returnFrames >= REQUIRED_STABLE_FRAMES) this.advance();
        }
        return this.complete
            ? { state: "complete" }
            : { state: "challenge", challenge: this.challenge, step: this.index + 1, total: this.sequence.length };
    }

    advance() {
        this.index += 1;
        if (this.index >= this.sequence.length) {
            this.state = "complete";
            return;
        }
        this.resetChallengeCounters();
        this.forwardYaw = null;
    }
}
