document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("id_signature_image");
    const video = document.getElementById("signature-camera-video");
    const canvas = document.getElementById("signature-camera-canvas");
    const preview = document.getElementById("registration-signature-preview");
    const placeholder = document.getElementById("signature-camera-placeholder");
    const startButton = document.getElementById("signature-camera-start");
    const captureButton = document.getElementById("signature-camera-capture");
    const retakeButton = document.getElementById("signature-camera-retake");
    const status = document.getElementById("registration-signature-upload-status");
    const error = document.getElementById("signature-camera-error");
    const form = document.querySelector(".registration-card form");

    if (
        !input || !video || !canvas || !preview || !placeholder ||
        !startButton || !captureButton || !retakeButton || !status || !error
    ) return;

    const MAX_BYTES = 2 * 1024 * 1024;
    const ANALYSIS_WIDTH = 240;
    const MIN_STABLE_FRAMES = 2;

    let stream = null;
    let previewUrl = null;
    let scanFrame = null;
    let lastScanAt = 0;
    let stableFrames = 0;
    let previousBox = null;
    let lastDetection = null;
    let capturing = false;
    let cameraStarting = false;

    const analysisCanvas = document.createElement("canvas");
    const analysisContext = analysisCanvas.getContext("2d", {
        willReadFrequently: true
    });

    function stopCamera() {
        if (scanFrame !== null) {
            cancelAnimationFrame(scanFrame);
            scanFrame = null;
        }

        if (stream) {
            stream.getTracks().forEach(function (track) {
                track.stop();
            });
            stream = null;
        }

        video.srcObject = null;
        captureButton.disabled = true;
    }

    function clearCapture() {
        input.value = "";

        if (previewUrl) {
            URL.revokeObjectURL(previewUrl);
            previewUrl = null;
        }

        preview.removeAttribute("src");
        preview.hidden = true;
        placeholder.hidden = false;
        retakeButton.hidden = true;

        lastDetection = null;
        previousBox = null;
        stableFrames = 0;
        capturing = false;

        status.textContent =
            "Place your handwritten signature on plain white paper.";
    }

    function setError(message) {
        error.textContent = message;
        error.hidden = false;
    }

    function closeBoxes(a, b) {
        if (!a || !b) return false;

        const scale = Math.max(
            1,
            Math.sqrt(a.width * a.height),
            Math.sqrt(b.width * b.height)
        );

        return (
            Math.abs(a.x - b.x) < scale * 0.06 &&
            Math.abs(a.y - b.y) < scale * 0.06 &&
            Math.abs(a.width - b.width) < scale * 0.08 &&
            Math.abs(a.height - b.height) < scale * 0.08
        );
    }

    /*
     * Heuristic detection:
     * - estimate the light-paper region;
     * - find dark/blue ink-like pixels surrounded by light pixels;
     * - reject detections that are too small or cover most of the frame.
     *
     * This is not a handwriting-recognition model.
     */
    function detectSignature(source) {
        const sourceWidth =
            source.naturalWidth || source.videoWidth || source.width;
        const sourceHeight =
            source.naturalHeight || source.videoHeight || source.height;

        if (!sourceWidth || !sourceHeight) return null;

        const ratio = sourceHeight / sourceWidth;
        analysisCanvas.width = ANALYSIS_WIDTH;
        analysisCanvas.height = Math.max(1, Math.round(ANALYSIS_WIDTH * ratio));

        analysisContext.drawImage(
            source, 0, 0, analysisCanvas.width, analysisCanvas.height
        );

        const width = analysisCanvas.width;
        const height = analysisCanvas.height;
        const pixels = analysisContext.getImageData(
            0, 0, width, height
        ).data;

        const light = new Uint8Array(width * height);
        let lightCount = 0;
        let minPaperX = width;
        let minPaperY = height;
        let maxPaperX = -1;
        let maxPaperY = -1;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const p = (y * width + x) * 4;
                const r = pixels[p];
                const g = pixels[p + 1];
                const b = pixels[p + 2];
                const brightness = (r + g + b) / 3;
                const spread = Math.max(r, g, b) - Math.min(r, g, b);

                if (brightness >= 175 && spread <= 105) {
                    const i = y * width + x;
                    light[i] = 1;
                    lightCount++;
                    minPaperX = Math.min(minPaperX, x);
                    minPaperY = Math.min(minPaperY, y);
                    maxPaperX = Math.max(maxPaperX, x);
                    maxPaperY = Math.max(maxPaperY, y);
                }
            }
        }

        if (
            lightCount < width * height * 0.20 ||
            maxPaperX <= minPaperX ||
            maxPaperY <= minPaperY
        ) return null;

        const paperWidth = maxPaperX - minPaperX + 1;
        const paperHeight = maxPaperY - minPaperY + 1;

        let minX = width;
        let minY = height;
        let maxX = -1;
        let maxY = -1;
        let inkCount = 0;

        const integralStride = width + 1;
                const lightIntegral = new Uint32Array(integralStride * (height + 1));
                for (let iy = 1; iy <= height; iy++) {
                    let rowSum = 0;
                    const lightRow = (iy - 1) * width;
                    const integralRow = iy * integralStride;
                    const previousRow = (iy - 1) * integralStride;
                    for (let ix = 1; ix <= width; ix++) {
                        rowSum += light[lightRow + ix - 1];
                        lightIntegral[integralRow + ix] =
                            lightIntegral[previousRow + ix] + rowSum;
                    }
                }

for (let y = minPaperY + 1; y < maxPaperY; y++) {
            for (let x = minPaperX + 1; x < maxPaperX; x++) {
                const p = (y * width + x) * 4;
                const r = pixels[p];
                const g = pixels[p + 1];
                const b = pixels[p + 2];
                const brightness = (r + g + b) / 3;

                const darkInk = brightness < 130;
                const blueInk = b > r * 1.20 && b > g * 1.05 &&
                    r < 145 && brightness < 155;

                if (!darkInk && !blueInk) continue;

                // Exclude dark background areas without nearby paper.
const left = Math.max(0, x - 2);
                const top = Math.max(0, y - 2);
                const right = Math.min(width - 1, x + 2);
                const bottom = Math.min(height - 1, y + 2);
                const nearbyLight =
                    lightIntegral[(bottom + 1) * integralStride + right + 1]
                    - lightIntegral[top * integralStride + right + 1]
                    - lightIntegral[(bottom + 1) * integralStride + left]
                    + lightIntegral[top * integralStride + left];
                if (nearbyLight < 9) continue;

                inkCount++;
                minX = Math.min(minX, x);
                minY = Math.min(minY, y);
                maxX = Math.max(maxX, x);
                maxY = Math.max(maxY, y);
            }
        }

        if (maxX < 0 || maxY < 0) return null;

        const inkWidth = maxX - minX + 1;
        const inkHeight = maxY - minY + 1;
        const inkRatio = inkCount / (paperWidth * paperHeight);

        if (
            inkWidth < paperWidth * 0.08 ||
            inkHeight < paperHeight * 0.015 ||
            inkWidth > paperWidth * 0.90 ||
            inkHeight > paperHeight * 0.65 ||
            inkRatio < 0.0005 ||
            inkRatio > 0.22
        ) return null;

        return {
            x: minX,
            y: minY,
            width: inkWidth,
            height: inkHeight,
            paperX: minPaperX,
            paperY: minPaperY,
            paperWidth: paperWidth,
            paperHeight: paperHeight,
            analysisWidth: width,
            analysisHeight: height
        };
    }

    const CAMERA_START_MAX_ATTEMPTS = 3;
    const CAMERA_RETRY_DELAY_MS = 700;

    function waitForCameraRelease(ms) {
        return new Promise(function (resolve) {
            window.setTimeout(resolve, ms);
        });
    }

    async function startCamera(attempt = 1) {
        if (cameraStarting) return;
        cameraStarting = true;

        if (!navigator.mediaDevices ||
            !navigator.mediaDevices.getUserMedia) {
            setError(
                "Camera access is unavailable. Open this page over HTTPS " +
                "in a supported browser."
            );
            cameraStarting = false;
            return;
        }

        stopCamera();
        clearCapture();

        // Allow the browser and device time to release the previous stream.
        await waitForCameraRelease(CAMERA_RETRY_DELAY_MS);
        error.hidden = true;
        status.textContent = "Waiting for camera permission…";

        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            });

            video.srcObject = stream;
            video.hidden = false;
            placeholder.hidden = true;
            await video.play();

            captureButton.disabled = false;
            status.textContent =
                "Place the entire signature on light paper in good light, " +
                "then tap Capture signature.";
            cameraStarting = false;
        } catch (exception) {
            stopCamera();

            if (
                exception &&
                exception.name === "NotReadableError" &&
                attempt < CAMERA_START_MAX_ATTEMPTS
            ) {
                status.textContent =
                    `Camera busy. Retrying (${attempt + 1}/` +
                    `${CAMERA_START_MAX_ATTEMPTS})…`;
                await waitForCameraRelease(CAMERA_RETRY_DELAY_MS);
                cameraStarting = false;
                return startCamera(attempt + 1);
            }

            console.error(
                "Signature camera startup failed:",
                exception.name,
                exception.message
            );
            setError(
                `Camera error: ${exception.name || "UnknownError"}. ` +
                `${exception.message || "Please try again."}`
            );
            cameraStarting = false;
        }
    }

    function captureSignature() {
        if (
            !stream || !video.videoWidth ||
            !video.videoHeight || capturing
        ) {
            return;
        }

        capturing = true;
        error.hidden = true;
        status.textContent = "Capturing photo…";

        const maxDimension = 1600;
        const scale = Math.min(
            1,
            maxDimension / Math.max(video.videoWidth, video.videoHeight)
        );
        const photoWidth = Math.round(video.videoWidth * scale);
        const photoHeight = Math.round(video.videoHeight * scale);

        canvas.width = photoWidth;
        canvas.height = photoHeight;

        const context = canvas.getContext("2d", { alpha: false });
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, photoWidth, photoHeight);
        context.drawImage(video, 0, 0, photoWidth, photoHeight);

        // Stop the camera immediately after the still image is captured.
        stopCamera();

        canvas.toBlob(function (photoBlob) {
            if (!photoBlob) {
                capturing = false;
                setError("The photo could not be captured. Please try again.");
                return;
            }

            const temporaryUrl = URL.createObjectURL(photoBlob);
            const photo = new Image();

            photo.onerror = function () {
                URL.revokeObjectURL(temporaryUrl);
                capturing = false;
                setError("The photo could not be read. Please retake it.");
            };

            photo.onload = function () {
                URL.revokeObjectURL(temporaryUrl);

                let detection = null;
                let averageBrightness = 0;

                try {
                    // The detector now analyses the captured photo, not video.
                    detection = detectSignature(photo);

                    const pixels = analysisContext.getImageData(
                        0, 0, analysisCanvas.width, analysisCanvas.height
                    ).data;

                    let total = 0;
                    let samples = 0;
                    for (let i = 0; i < pixels.length; i += 4 * 16) {
                        total += (
                            pixels[i] + pixels[i + 1] + pixels[i + 2]
                        ) / 3;
                        samples++;
                    }
                    averageBrightness = samples ? total / samples : 0;
                } catch (exception) {
                    console.warn("Signature photo scan failed:", exception);
                }

                function showRejectedPhoto(message) {
                    input.value = "";

                    if (previewUrl) URL.revokeObjectURL(previewUrl);
                    previewUrl = URL.createObjectURL(photoBlob);
                    preview.src = previewUrl;
                    preview.hidden = false;
                    video.hidden = true;
                    placeholder.hidden = true;
                    retakeButton.hidden = false;

                    status.textContent =
                        "Photo not accepted. Retake it after correcting the issue.";
                    setError(message);
                    capturing = false;
                }

                if (!detection) {
                    if (averageBrightness > 0 && averageBrightness < 105) {
                        showRejectedPhoto(
                            "The photo looks too dark. Move to brighter, even " +
                            "lighting, avoid shadows, and retake the signature."
                        );
                    } else {
                        showRejectedPhoto(
                            "A clear signature on light paper was not detected. " +
                            "Use plain white or light-brown paper, make sure the " +
                            "whole signature is visible and in focus, and retake it."
                        );
                    }
                    return;
                }

                // Convert detected paper coordinates into photo coordinates.
                const factorX = photo.naturalWidth / detection.analysisWidth;
                const factorY = photo.naturalHeight / detection.analysisHeight;
                const marginX = Math.max(
                    4, Math.round(detection.paperWidth * 0.035)
                );
                const marginY = Math.max(
                    4, Math.round(detection.paperHeight * 0.06)
                );

                let sx = Math.floor((detection.paperX - marginX) * factorX);
                let sy = Math.floor((detection.paperY - marginY) * factorY);
                let ex = Math.ceil(
                    (detection.paperX + detection.paperWidth + marginX) * factorX
                );
                let ey = Math.ceil(
                    (detection.paperY + detection.paperHeight + marginY) * factorY
                );

                sx = Math.max(0, sx);
                sy = Math.max(0, sy);
                ex = Math.min(photo.naturalWidth, ex);
                ey = Math.min(photo.naturalHeight, ey);

                const cropWidth = ex - sx;
                const cropHeight = ey - sy;

                if (cropWidth < 80 || cropHeight < 35) {
                    showRejectedPhoto(
                        "The signature appears too small. Move the camera closer " +
                        "while keeping the entire signature visible, then retake it."
                    );
                    return;
                }

                canvas.width = cropWidth;
                canvas.height = cropHeight;

                const cropContext = canvas.getContext("2d", { alpha: false });
                cropContext.fillStyle = "#ffffff";
                cropContext.fillRect(0, 0, cropWidth, cropHeight);
                cropContext.drawImage(
                    photo,
                    sx, sy, cropWidth, cropHeight,
                    0, 0, cropWidth, cropHeight
                );

                canvas.toBlob(function (blob) {
                    if (!blob) {
                        showRejectedPhoto(
                            "The signature crop could not be created. Please retake the photo."
                        );
                        return;
                    }

                    if (blob.size > MAX_BYTES) {
                        showRejectedPhoto(
                            "The cropped signature exceeds the 2 MB limit. " +
                            "Move closer to the paper and retake the photo."
                        );
                        return;
                    }

                    const file = new File([blob], "camera-signature.jpg", {
                        type: "image/jpeg",
                        lastModified: Date.now()
                    });

                    const transfer = new DataTransfer();
                    transfer.items.add(file);
                    input.files = transfer.files;

                    if (previewUrl) URL.revokeObjectURL(previewUrl);
                    previewUrl = URL.createObjectURL(blob);
                    preview.src = previewUrl;
                    preview.hidden = false;
                    video.hidden = true;
                    placeholder.hidden = true;
                    retakeButton.hidden = false;
                    error.hidden = true;
                    status.textContent =
                        "Signature detected and cropped. Review the preview before continuing.";
                    capturing = false;
                }, "image/jpeg", 0.88);
            };

            photo.src = temporaryUrl;
        }, "image/jpeg", 0.88);
    }

    startButton.addEventListener("click", startCamera);

    captureButton.addEventListener("click", captureSignature);

    retakeButton.addEventListener("click", startCamera);

    if (form) {
        form.addEventListener("submit", function (event) {
            if (!input.files || !input.files.length) {
                event.preventDefault();
                setError("Capture your handwritten signature before submitting.");
                startButton.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
                startButton.focus();
            }
        });
    }

    window.addEventListener("pagehide", stopCamera);
});
