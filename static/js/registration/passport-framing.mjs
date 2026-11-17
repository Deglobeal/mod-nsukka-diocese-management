export const PASSPORT_FRAME_WIDTH = 720;
export const PASSPORT_FRAME_HEIGHT = 900;

export function coverRect(sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    if ([sourceWidth, sourceHeight, targetWidth, targetHeight].some((value) =>
        !Number.isFinite(value) || value <= 0
    )) return null;

    const targetAspect = targetWidth / targetHeight;
    let x = 0;
    let y = 0;
    let width = sourceWidth;
    let height = sourceHeight;
    if (sourceWidth / sourceHeight > targetAspect) {
        width = sourceHeight * targetAspect;
        x = (sourceWidth - width) / 2;
    } else {
        height = sourceWidth / targetAspect;
        y = (sourceHeight - height) / 2;
    }
    return { x, y, width, height, scale: targetWidth / width };
}

export function passportCanvasRenderPlan(sourceWidth, sourceHeight) {
    return {
        width: PASSPORT_FRAME_WIDTH,
        height: PASSPORT_FRAME_HEIGHT,
        frame: coverRect(sourceWidth, sourceHeight)
    };
}

export function mapRectToCoverFrame(rect, sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    const crop = coverRect(sourceWidth, sourceHeight, targetWidth, targetHeight);
    if (!crop || !rect) return null;
    return {
        x: (rect.x - crop.x) / crop.width,
        y: (rect.y - crop.y) / crop.height,
        width: rect.width / crop.width,
        height: rect.height / crop.height
    };
}

export function mirrorRectHorizontally(rect, sourceWidth) {
    if (!rect || !Number.isFinite(sourceWidth) || sourceWidth <= 0) return null;
    return { ...rect, x: sourceWidth - rect.x - rect.width };
}

export function getPassportFaceGuidance(face, roll = 0, previous = null) {
    if (!face) return "no-face";
    const centerX = face.x + face.width / 2;
    const centerY = face.y + face.height / 2;

    const tooClose = face.height > 0.55;
    const stillLeavingCloseZone = face.height >= 0.50;
    if (previous === "farther" ? stillLeavingCloseZone : tooClose) return "farther";

    const tooFar = face.height < 0.30;
    const stillLeavingFarZone = face.height <= 0.35;
    if (previous === "closer" ? stillLeavingFarZone : tooFar) return "closer";
    if (Number.isFinite(roll) && Math.abs(roll) > 0.18) return "straight";
    if (face.x < 0.16 || centerX < 0.38) return "right";
    if (face.x + face.width > 0.84 || centerX > 0.62) return "left";
    if (face.y < 0.05 || centerY < 0.35) return "down";
    if (face.y + face.height > 0.95 || centerY > 0.65) return "up";
    return "ready";
}

export function isFaceSafeDuringLivenessChallenge(face) {
    if (!face) return false;
    return face.height >= 0.25 && face.height <= 0.65 &&
        face.x >= 0.02 && face.y >= 0.02 &&
        face.x + face.width <= 0.98 && face.y + face.height <= 0.96;
}

export function nextFacingMode(current) {
    return current === "environment" ? "user" : "environment";
}

export function stopMediaTracks(stream) {
    if (!stream || typeof stream.getTracks !== "function") return;
    stream.getTracks().forEach((track) => {
        if (track && typeof track.stop === "function") track.stop();
    });
}

export function cameraConstraintFallbacks(facingMode) {
    return [
        {
            audio: false,
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 720 },
                height: { ideal: 900 },
                aspectRatio: { ideal: 4 / 5 }
            }
        },
        {
            audio: false,
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 640 },
                height: { ideal: 800 },
                aspectRatio: { ideal: 4 / 5 }
            }
        },
        { audio: false, video: { facingMode } }
    ];
}

export function zoomConstraintTarget(capabilities, settings = {}) {
    const zoom = capabilities && capabilities.zoom;
    if (!zoom || !Number.isFinite(zoom.min) || !Number.isFinite(zoom.max) ||
        zoom.max <= zoom.min) return null;
    const current = Number.isFinite(settings.zoom) ? settings.zoom : null;
    return current === null || current > zoom.min + 0.01 ? zoom.min : null;
}

export function selectPreferredCameraDevice(devices, facingMode, currentDeviceId = "") {
    if (!Array.isArray(devices)) return null;
    const videoDevices = devices.filter((device) =>
        device && device.kind === "videoinput" && device.deviceId
    );
    const current = videoDevices.find((device) => device.deviceId === currentDeviceId);

    if (facingMode === "user") {
        const frontPattern = /front|user|selfie/i;
        const fronts = videoDevices.filter((device) => frontPattern.test(device.label || ""));
        const wide = fronts.find((device) => /ultra[ -]?wide|\bwide\b|0\.5\s*x/i.test(device.label || ""));
        if (wide) return wide.deviceId !== currentDeviceId ? wide : null;
        const frontNonWide = fronts.find((device) => device.deviceId !== currentDeviceId &&
            !/tele|zoom/i.test(device.label || ""));
        return current && /tele|zoom/i.test(current.label || "") ? frontNonWide || null : null;
    }

    const rearPattern = /back|rear|environment|wide|main|primary/i;
    const rejectPattern = /tele|macro|depth|ultra|periscope/i;
    const labelledRear = videoDevices.filter((device) =>
        rearPattern.test(device.label || "") && !rejectPattern.test(device.label || "")
    );
    const mainRear = labelledRear.find((device) =>
        /main|primary/i.test(device.label || "") && device.deviceId !== currentDeviceId
    );
    if (mainRear) return mainRear;

    // Keep the browser-chosen environment device unless its label identifies
    // a lens that should not be used as the primary passport camera.
    if (current && rejectPattern.test(current.label || "")) {
        return labelledRear.find((device) => device.deviceId !== currentDeviceId) || null;
    }
    return null;
}
