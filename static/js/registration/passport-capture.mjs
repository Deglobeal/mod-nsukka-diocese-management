export const CAPTURE_STABILITY_MS = 1500;

export function isCaptureEligible({
    faceCount,
    positioned,
    livenessPassed,
    facingForward,
    glassesCheckPassed,
    lightingAdequate,
    stableForMs,
    captureInProgress
}) {
    return faceCount === 1 && positioned === true &&
        livenessPassed === true && facingForward === true &&
        glassesCheckPassed === true && lightingAdequate === true &&
        Number.isFinite(stableForMs) && stableForMs >= CAPTURE_STABILITY_MS &&
        captureInProgress !== true;
}

export class AutoCaptureCountdown {
    constructor(durationMs = 3000) {
        this.durationMs = durationMs;
        this.dueAt = null;
        this.fired = false;
    }

    cancel() {
        this.dueAt = null;
        this.fired = false;
    }

    update(eligible, enabled, now) {
        if (!eligible || !enabled) {
            this.cancel();
            return { state: enabled ? "waiting" : "manual" };
        }
        if (this.fired) return { state: "fired" };
        if (this.dueAt === null) this.dueAt = now + this.durationMs;
        const remainingMs = Math.max(0, this.dueAt - now);
        if (remainingMs === 0) {
            this.fired = true;
            return { state: "capture", seconds: 0 };
        }
        return {
            state: "countdown",
            seconds: Math.ceil(remainingMs / 1000)
        };
    }
}
