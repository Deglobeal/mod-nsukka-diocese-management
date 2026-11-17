import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
    buildConfidenceMaskImageData,
    confidenceToAlpha,
    createPassportPhotoProcessor,
    MAX_PHOTO_BYTES,
    SELFIE_SEGMENTER_MODEL_URL
} from "../../static/js/registration/passport-background-removal.mjs";

function makeCanvasHarness() {
    const canvases = [];
    const operations = [];
    function createCanvas() {
        const context = {
            globalCompositeOperation: "source-over",
            fillStyle: "",
            createImageData(width, height) {
                return { width, height, data: new Uint8ClampedArray(width * height * 4) };
            },
            putImageData(imageData) {
                operations.push({ type: "mask", imageData });
            },
            drawImage(...args) {
                operations.push({
                    type: "draw",
                    operation: this.globalCompositeOperation,
                    args
                });
            },
            fillRect(...args) {
                operations.push({
                    type: "fill",
                    color: this.fillStyle,
                    operation: this.globalCompositeOperation,
                    args
                });
            }
        };
        const canvas = {
            width: 0,
            height: 0,
            getContext: () => context,
            toBlob(callback, type, quality) {
                operations.push({ type: "export", quality });
                callback(new Blob(["jpeg"], { type }));
            }
        };
        canvases.push(canvas);
        return canvas;
    }
    return { canvases, operations, createCanvas };
}

function makeMask(values = [0, 0.5, 1, 1]) {
    return {
        width: 2,
        height: 2,
        closed: false,
        getAsFloat32Array: () => new Float32Array(values),
        close() { this.closed = true; }
    };
}

test("confidence mask maps background to transparent and soft edges to blended alpha", () => {
    assert.equal(confidenceToAlpha(0), 0);
    assert.ok(confidenceToAlpha(0.48) > 100 && confidenceToAlpha(0.48) < 160);
    assert.equal(confidenceToAlpha(1), 255);

    const result = buildConfidenceMaskImageData(
        { width: 2, height: 1, getAsFloat32Array: () => new Float32Array([0, 1]) },
        (width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) })
    );
    assert.deepEqual([...result.data], [255, 255, 255, 0, 255, 255, 255, 255]);
});

test("mocked MediaPipe segmentation composites the subject onto white and preserves dimensions", async () => {
    const source = { width: 320, height: 400 };
    const mask = makeMask();
    const { canvases, operations, createCanvas } = makeCanvasHarness();
    const segmenter = {
        calls: 0,
        segment(image) {
            this.calls += 1;
            assert.equal(image, source);
            return { confidenceMasks: [mask] };
        }
    };
    const statuses = [];
    const processPhoto = createPassportPhotoProcessor({
        getSegmenter: async (onStatus) => {
            onStatus("Loading mocked model…");
            return segmenter;
        },
        createCanvas,
        decodeSource: async (value) => ({ image: value })
    });

    const jpeg = await processPhoto(source, (message) => statuses.push(message));

    assert.equal(jpeg.type, "image/jpeg");
    assert.ok(jpeg.size <= MAX_PHOTO_BYTES);
    assert.equal(segmenter.calls, 1);
    assert.equal(canvases[1].width, 320);
    assert.equal(canvases[1].height, 400);
    assert.ok(operations.some((op) => op.type === "draw" && op.operation === "destination-in"));
    assert.ok(operations.some((op) => op.type === "fill" && op.color === "#FFFFFF"));
    assert.equal(mask.closed, true);
    assert.match(statuses.join(" "), /Loading mocked model/);
    assert.match(statuses.join(" "), /complete/);
});

test("model and segmentation failures are retryable and never return the source image", async () => {
    const source = { width: 320, height: 400 };
    let attempts = 0;
    const { createCanvas } = makeCanvasHarness();
    const processPhoto = createPassportPhotoProcessor({
        getSegmenter: async () => {
            attempts += 1;
            if (attempts === 1) throw new Error("WASM stack detail");
            return { segment: () => ({ confidenceMasks: [] }) };
        },
        createCanvas,
        decodeSource: async (value) => ({ image: value })
    });

    const originalConsoleError = console.error;
    console.error = () => {};
    try {
        await assert.rejects(
            processPhoto(source),
            /background-removal model could not load/
        );
        await assert.rejects(
            processPhoto(source),
            /person could not be separated/
        );
    } finally {
        console.error = originalConsoleError;
    }
    assert.equal(attempts, 2);
});

test("same processor accepts camera canvases and selected image sources", async () => {
    const cameraCanvas = { width: 320, height: 400, sourceType: "camera" };
    const selectedFile = { width: 320, height: 400, sourceType: "upload" };
    const seen = [];
    const { createCanvas } = makeCanvasHarness();
    const processPhoto = createPassportPhotoProcessor({
        getSegmenter: async () => ({
            segment(image) {
                seen.push(image.sourceType);
                return { confidenceMasks: [makeMask([1, 1, 1, 1])] };
            }
        }),
        createCanvas,
        decodeSource: async (value) => ({ image: value })
    });

    await processPhoto(cameraCanvas);
    await processPhoto(selectedFile);
    assert.deepEqual(seen, ["camera", "upload"]);
});

test("processor rejects out-of-range dimensions without loading the model", async () => {
    let modelLoads = 0;
    const processPhoto = createPassportPhotoProcessor({
        getSegmenter: async () => {
            modelLoads += 1;
            throw new Error("should not load");
        },
        decodeSource: async (value) => ({ image: value })
    });

    await assert.rejects(
        processPhoto({ width: 5000, height: 100 }),
        /100 and 4000 pixels/
    );
    assert.equal(modelLoads, 0);
});

test("camera processing uses automatic capture and blocks duplicate form submission", () => {
    const script = readFileSync(
        new URL("../../static/js/registration/passport-camera.js", import.meta.url),
        "utf8"
    );
    const template = readFileSync(
        new URL("../../templates/registration/registration.html", import.meta.url),
        "utf8"
    );
    assert.match(script, /processPhotoSource\(photoCanvas, "camera"\)/);
    assert.match(script, /autoCaptureCountdown\.update\([\s\S]*?true,[\s\S]*?timestamp\)/);
    assert.match(script, /countdown\.state === "capture"[\s\S]*?capturePhoto\(\)/);
    assert.match(script, /if \(photoCaptureInProgress\) return/);
    assert.match(script, /if \(photoCaptureInProgress\) \{[\s\S]*?event\.preventDefault\(\)/);
    assert.doesNotMatch(script, /passport-camera-capture|passport-auto-capture/);
    assert.doesNotMatch(template, /passport-camera-capture|passport-auto-capture|passport-photo-upload/);
});

test("segmentation model URL is pinned to the versioned Google model path", () => {
    assert.match(SELFIE_SEGMENTER_MODEL_URL, /selfie_segmenter\/float16\/1\/selfie_segmenter\.tflite$/);
    const source = readFileSync(
        new URL("../../static/js/registration/passport-background-removal.mjs", import.meta.url),
        "utf8"
    );
    assert.match(source, /runningMode:\s*["']IMAGE["']/);
    assert.match(source, /outputConfidenceMasks:\s*true/);
    assert.match(source, /TASKS_VISION_VERSION\s*=\s*["']0\.10\.14["']/);
    assert.match(source, /cdn\.jsdelivr\.net\/npm\/\@mediapipe\/tasks-vision@\$\{TASKS_VISION_VERSION\}/);
});
