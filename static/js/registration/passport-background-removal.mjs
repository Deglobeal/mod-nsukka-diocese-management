const TASKS_VISION_VERSION = "0.10.14";
const TASKS_VISION_MODULE_URL =
    `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${TASKS_VISION_VERSION}/+esm`;
const TASKS_VISION_WASM_URL =
    `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${TASKS_VISION_VERSION}/wasm`;
export const SELFIE_SEGMENTER_MODEL_URL =
    "https://storage.googleapis.com/mediapipe-models/" +
    "image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite";

export const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
export const MIN_PHOTO_DIMENSION = 100;
export const MAX_PHOTO_DIMENSION = 4000;

let visionRuntimePromise = null;
let imageSegmenterPromise = null;

export function confidenceToAlpha(confidence) {
    if (!Number.isFinite(confidence)) {
        throw new Error("The segmentation mask contains invalid values.");
    }

    // Keep uncertain boundary pixels partially transparent for hair detail,
    // while suppressing low-confidence background pixels.
    const low = 0.24;
    const high = 0.72;
    const amount = Math.max(0, Math.min(1, (confidence - low) / (high - low)));
    return Math.round(amount * amount * (3 - 2 * amount) * 255);
}

export function buildConfidenceMaskImageData(mask, createImageData) {
    const width = Number(mask && mask.width);
    const height = Number(mask && mask.height);
    const values = mask && mask.getAsFloat32Array
        ? mask.getAsFloat32Array()
        : null;

    if (
        !Number.isInteger(width) || !Number.isInteger(height) ||
        width < 1 || height < 1 || !values || values.length !== width * height
    ) {
        throw new Error("The segmentation mask could not be read.");
    }

    const imageData = createImageData(width, height);
    const pixels = imageData.data;
    for (let index = 0; index < values.length; index += 1) {
        const offset = index * 4;
        pixels[offset] = 255;
        pixels[offset + 1] = 255;
        pixels[offset + 2] = 255;
        pixels[offset + 3] = confidenceToAlpha(values[index]);
    }
    return imageData;
}

export function loadMediaPipeVisionRuntime() {
    if (!visionRuntimePromise) {
        visionRuntimePromise = (async function () {
            const vision = await import(TASKS_VISION_MODULE_URL);
            const files = await vision.FilesetResolver.forVisionTasks(
                TASKS_VISION_WASM_URL
            );
            return { vision, files };
        })().catch(function (error) {
            visionRuntimePromise = null;
            throw error;
        });
    }
    return visionRuntimePromise;
}

export async function loadPassportImageSegmenter(onStatus = () => {}) {
    if (!imageSegmenterPromise) {
        onStatus("Loading the passport background-removal model…");
        imageSegmenterPromise = (async function () {
            const { vision, files } = await loadMediaPipeVisionRuntime();
            return vision.ImageSegmenter.createFromOptions(files, {
                baseOptions: { modelAssetPath: SELFIE_SEGMENTER_MODEL_URL },
                // Tasks Vision web examples use the string mode value. The
                // package does not expose a stable `RunningMode` runtime enum.
                runningMode: "IMAGE",
                outputCategoryMask: false,
                outputConfidenceMasks: true
            });
        })().catch(function (error) {
            imageSegmenterPromise = null;
            throw error;
        });
    } else {
        onStatus("Loading the passport background-removal model…");
    }
    return imageSegmenterPromise;
}

function imageDimensions(image) {
    return {
        width: image.naturalWidth || image.videoWidth || image.width,
        height: image.naturalHeight || image.videoHeight || image.height
    };
}

async function decodePhotoSource(source) {
    if (typeof Blob !== "undefined" && source instanceof Blob) {
        if (typeof createImageBitmap === "function") {
            try {
                return {
                    image: await createImageBitmap(source, {
                        imageOrientation: "from-image"
                    }),
                    shouldClose: true
                };
            } catch (error) {
                // Some Safari releases accept createImageBitmap but not its
                // orientation options; the image-element fallback handles them.
            }
        }

        if (typeof Image === "undefined" || typeof URL === "undefined") {
            throw new Error("This browser cannot open the selected photograph.");
        }
        const objectUrl = URL.createObjectURL(source);
        try {
            const image = new Image();
            await new Promise((resolve, reject) => {
                image.onload = resolve;
                image.onerror = reject;
                image.src = objectUrl;
            });
            return { image, shouldClose: false, objectUrl };
        } catch (error) {
            URL.revokeObjectURL(objectUrl);
            throw error;
        }
    }
    return { image: source, shouldClose: false };
}

function canvasToJpeg(canvas, quality) {
    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (!blob || blob.type !== "image/jpeg") {
                reject(new Error("The processed photograph could not be exported."));
                return;
            }
            resolve(blob);
        }, "image/jpeg", quality);
    });
}

export function createPassportPhotoProcessor({
    getSegmenter = loadPassportImageSegmenter,
    createCanvas = () => document.createElement("canvas"),
    decodeSource = decodePhotoSource
} = {}) {
    return async function processPassportPhotoBackground(source, onStatus = () => {}) {
        let decoded = null;
        let result = null;
        let stage = "image preparation";
        try {
            onStatus("Preparing the photograph…");
            decoded = await decodeSource(source);
            const image = decoded.image;
            const { width, height } = imageDimensions(image);
            if (
                !Number.isInteger(width) || !Number.isInteger(height) ||
                width < MIN_PHOTO_DIMENSION || height < MIN_PHOTO_DIMENSION ||
                width > MAX_PHOTO_DIMENSION || height > MAX_PHOTO_DIMENSION
            ) {
                throw new Error(
                    "Use a photograph between 100 and 4000 pixels in each dimension."
                );
            }

            stage = "MediaPipe model loading";
            const segmenter = await getSegmenter(onStatus);
            stage = "person segmentation";
            onStatus("Removing the background from your photograph…");
            result = segmenter.segment(image);
            const confidenceMasks = result && result.confidenceMasks;
            const personMask = confidenceMasks && confidenceMasks.length === 1
                ? confidenceMasks[0]
                : confidenceMasks && confidenceMasks[1];
            if (!personMask) {
                throw new Error("The person could not be separated from the background.");
            }

            const maskCanvas = createCanvas();
            maskCanvas.width = personMask.width;
            maskCanvas.height = personMask.height;
            const maskContext = maskCanvas.getContext("2d", {
                willReadFrequently: false
            });
            if (!maskContext || !maskCanvas.width || !maskCanvas.height) {
                throw new Error("Background removal is unavailable in this browser.");
            }
            const maskImageData = buildConfidenceMaskImageData(
                personMask,
                (maskWidth, maskHeight) => maskContext.createImageData(
                    maskWidth,
                    maskHeight
                )
            );
            maskContext.putImageData(maskImageData, 0, 0);

            stage = "photo compositing";
            const outputCanvas = createCanvas();
            outputCanvas.width = width;
            outputCanvas.height = height;
            const outputContext = outputCanvas.getContext("2d");
            if (!outputContext) {
                throw new Error("Background removal is unavailable in this browser.");
            }
            outputContext.drawImage(image, 0, 0, width, height);
            outputContext.globalCompositeOperation = "destination-in";
            outputContext.drawImage(maskCanvas, 0, 0, width, height);
            outputContext.globalCompositeOperation = "destination-over";
            outputContext.fillStyle = "#FFFFFF";
            outputContext.fillRect(0, 0, width, height);
            outputContext.globalCompositeOperation = "source-over";

            stage = "JPEG export";
            for (const quality of [0.92, 0.88, 0.82, 0.76]) {
                const blob = await canvasToJpeg(outputCanvas, quality);
                if (blob.size <= MAX_PHOTO_BYTES) {
                    onStatus("Background removal complete. Review your photograph.");
                    return blob;
                }
            }
            throw new Error("The processed photograph exceeds the 5 MB limit.");
        } catch (error) {
            const diagnostic = {
                stage,
                name: error instanceof Error ? error.name : "UnknownError",
                message: error instanceof Error ? error.message : String(error)
            };
            // This contains processing diagnostics only; never log image data or
            // applicant details. It lets support identify CDN/model/browser errors.
            console.error("Passport photo background removal failed.", diagnostic);

            const knownUserMessages = new Set([
                "This browser cannot open the selected photograph.",
                "Use a photograph between 100 and 4000 pixels in each dimension.",
                "The segmentation mask contains invalid values.",
                "The segmentation mask could not be read.",
                "The person could not be separated from the background.",
                "Background removal is unavailable in this browser.",
                "The processed photograph could not be exported.",
                "The processed photograph exceeds the 5 MB limit."
            ]);
            if (error instanceof Error && knownUserMessages.has(error.message)) {
                throw error;
            }
            if (stage === "MediaPipe model loading") {
                throw new Error(
                    "The background-removal model could not load. Check your connection and retry, or choose another photo."
                );
            }
            if (stage === "person segmentation") {
                throw new Error(
                    "The person could not be separated from this photo. Please retry or choose another photo."
                );
            }
            throw new Error(
                "Background removal could not be completed. Please retry or choose another photo."
            );
        } finally {
            if (result && typeof result.close === "function") {
                result.close();
            } else if (result && result.confidenceMasks) {
                result.confidenceMasks.forEach((mask) => {
                    if (mask && typeof mask.close === "function") mask.close();
                });
            }
            if (decoded && decoded.shouldClose && decoded.image.close) {
                decoded.image.close();
            }
            if (decoded && decoded.objectUrl) {
                URL.revokeObjectURL(decoded.objectUrl);
            }
        }
    };
}

export const removePassportPhotoBackground = createPassportPhotoProcessor();
