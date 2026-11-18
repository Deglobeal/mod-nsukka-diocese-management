export const MIN_CROP_SIZE = 40;
export const MAX_SIGNATURE_BYTES = 2 * 1024 * 1024;

function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
}

function validBounds(bounds) {
    return bounds && Number.isFinite(bounds.width) &&
        Number.isFinite(bounds.height) && bounds.width > 0 && bounds.height > 0;
}

export function constrainCropRect(rect, bounds, minimum = MIN_CROP_SIZE) {
    if (!validBounds(bounds)) {
        throw new Error("The signature crop area is unavailable.");
    }
    const minWidth = Math.min(minimum, bounds.width);
    const minHeight = Math.min(minimum, bounds.height);
    const width = clamp(Number(rect.width) || minWidth, minWidth, bounds.width);
    const height = clamp(Number(rect.height) || minHeight, minHeight, bounds.height);
    const x = clamp(Number(rect.x) || 0, 0, bounds.width - width);
    const y = clamp(Number(rect.y) || 0, 0, bounds.height - height);
    return { x, y, width, height };
}

export function initialCropRect(bounds) {
    if (!validBounds(bounds)) {
        throw new Error("The signature crop area is unavailable.");
    }
    return constrainCropRect({
        x: bounds.width * 0.04,
        y: bounds.height * 0.04,
        width: bounds.width * 0.92,
        height: bounds.height * 0.92
    }, bounds);
}

export function moveCropRect(start, deltaX, deltaY, bounds) {
    return constrainCropRect({
        ...start,
        x: start.x + deltaX,
        y: start.y + deltaY
    }, bounds);
}

export function resizeCropRect(
    start,
    handle,
    deltaX,
    deltaY,
    bounds,
    minimum = MIN_CROP_SIZE
) {
    if (!validBounds(bounds)) {
        throw new Error("The signature crop area is unavailable.");
    }
    const minWidth = Math.min(minimum, bounds.width);
    const minHeight = Math.min(minimum, bounds.height);
    let left = start.x;
    let top = start.y;
    let right = start.x + start.width;
    let bottom = start.y + start.height;

    if (handle.includes("w")) {
        left = clamp(start.x + deltaX, 0, right - minWidth);
    }
    if (handle.includes("e")) {
        right = clamp(start.x + start.width + deltaX, left + minWidth, bounds.width);
    }
    if (handle.includes("n")) {
        top = clamp(start.y + deltaY, 0, bottom - minHeight);
    }
    if (handle.includes("s")) {
        bottom = clamp(start.y + start.height + deltaY, top + minHeight, bounds.height);
    }

    return { x: left, y: top, width: right - left, height: bottom - top };
}

export function mapCropRectToSource(rect, renderedBounds, naturalWidth, naturalHeight) {
    if (
        !validBounds(renderedBounds) ||
        !Number.isFinite(naturalWidth) || !Number.isFinite(naturalHeight) ||
        naturalWidth < 1 || naturalHeight < 1
    ) {
        throw new Error("The captured signature photograph could not be measured.");
    }

    const crop = constrainCropRect(rect, renderedBounds, 1);
    const scaleX = naturalWidth / renderedBounds.width;
    const scaleY = naturalHeight / renderedBounds.height;
    const left = clamp(Math.floor(crop.x * scaleX), 0, naturalWidth - 1);
    const top = clamp(Math.floor(crop.y * scaleY), 0, naturalHeight - 1);
    const right = clamp(Math.ceil((crop.x + crop.width) * scaleX), left + 1, naturalWidth);
    const bottom = clamp(Math.ceil((crop.y + crop.height) * scaleY), top + 1, naturalHeight);

    return {
        x: left,
        y: top,
        width: right - left,
        height: bottom - top
    };
}

function canvasToJpeg(canvas, quality) {
    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (!blob || blob.type !== "image/jpeg") {
                reject(new Error("The cropped signature could not be encoded as JPEG."));
                return;
            }
            resolve(blob);
        }, "image/jpeg", quality);
    });
}

export async function exportSignatureCrop(
    sourceImage,
    rect,
    renderedBounds,
    {
        createCanvas = () => document.createElement("canvas"),
        maxBytes = MAX_SIGNATURE_BYTES
    } = {}
) {
    const sourceRect = mapCropRectToSource(
        rect,
        renderedBounds,
        sourceImage.naturalWidth,
        sourceImage.naturalHeight
    );
    const canvas = createCanvas();
    canvas.width = sourceRect.width;
    canvas.height = sourceRect.height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
        throw new Error("Signature cropping is unavailable in this browser.");
    }
    context.drawImage(
        sourceImage,
        sourceRect.x,
        sourceRect.y,
        sourceRect.width,
        sourceRect.height,
        0,
        0,
        sourceRect.width,
        sourceRect.height
    );

    for (const quality of [0.92, 0.88, 0.82, 0.76, 0.70, 0.64]) {
        const blob = await canvasToJpeg(canvas, quality);
        if (blob.size <= maxBytes) return blob;
    }
    throw new Error(
        "The cropped JPEG exceeds 2 MB. Adjust the crop or retake the photograph."
    );
}
