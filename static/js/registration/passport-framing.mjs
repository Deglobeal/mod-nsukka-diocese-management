export const PASSPORT_FRAME_WIDTH = 720;
export const PASSPORT_FRAME_HEIGHT = 900;

export function containRect(sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    if ([sourceWidth, sourceHeight, targetWidth, targetHeight].some((value) =>
        !Number.isFinite(value) || value <= 0
    )) return null;

    const scale = Math.min(targetWidth / sourceWidth, targetHeight / sourceHeight);
    const width = sourceWidth * scale;
    const height = sourceHeight * scale;
    return {
        x: (targetWidth - width) / 2,
        y: (targetHeight - height) / 2,
        width,
        height,
        scale
    };
}

export function passportCanvasRenderPlan(sourceWidth, sourceHeight) {
    return {
        width: PASSPORT_FRAME_WIDTH,
        height: PASSPORT_FRAME_HEIGHT,
        frame: containRect(sourceWidth, sourceHeight)
    };
}

export function mapRectToContainFrame(rect, sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    const fit = containRect(sourceWidth, sourceHeight, targetWidth, targetHeight);
    if (!fit || !rect) return null;
    return {
        x: (fit.x + rect.x * fit.scale) / targetWidth,
        y: (fit.y + rect.y * fit.scale) / targetHeight,
        width: (rect.width * fit.scale) / targetWidth,
        height: (rect.height * fit.scale) / targetHeight
    };
}

export function getPassportFaceGuidance(face) {
    if (!face) return "no-face";
    const centerX = face.x + face.width / 2;
    const centerY = face.y + face.height / 2;

    if (face.width < 0.14 || face.height < 0.18) return "closer";
    if (face.width > 0.40 || face.height > 0.46) return "farther";
    if (face.x < 0.16 || centerX < 0.38) return "right";
    if (face.x + face.width > 0.84 || centerX > 0.62) return "left";
    if (face.y < 0.04 || centerY < 0.20) return "down";
    if (face.y + face.height > 0.50 || centerY > 0.38) return "up";
    return "ready";
}

export function nextFacingMode(current) {
    return current === "environment" ? "user" : "environment";
}

export function cameraConstraintFallbacks(facingMode) {
    return [
        {
            audio: false,
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 720 },
                height: { ideal: 1280 }
            }
        },
        { audio: false, video: { facingMode: { ideal: facingMode } } },
        { audio: false, video: true }
    ];
}
