import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
    constrainCropRect,
    exportSignatureCrop,
    initialCropRect,
    mapCropRectToSource,
    moveCropRect,
    resizeCropRect
} from "../../static/js/registration/signature-crop.mjs";

test("initial crop stays inside portrait and landscape photographs", () => {
    for (const bounds of [{ width: 320, height: 480 }, { width: 640, height: 360 }]) {
        const crop = initialCropRect(bounds);
        assert.ok(crop.x >= 0 && crop.y >= 0);
        assert.ok(crop.x + crop.width <= bounds.width);
        assert.ok(crop.y + crop.height <= bounds.height);
        assert.ok(crop.width < bounds.width && crop.height < bounds.height);
    }
});

test("move and free-ratio resize clamp crop within displayed bounds", () => {
    const bounds = { width: 300, height: 200 };
    const start = { x: 40, y: 30, width: 100, height: 70 };
    assert.deepEqual(moveCropRect(start, 500, -100, bounds), {
        x: 200, y: 0, width: 100, height: 70
    });
    const wider = resizeCropRect(start, "e", 50, 0, bounds);
    assert.deepEqual(wider, { x: 40, y: 30, width: 150, height: 70 });
    const taller = resizeCropRect(start, "s", 0, 40, bounds);
    assert.deepEqual(taller, { x: 40, y: 30, width: 100, height: 110 });
    assert.deepEqual(
        resizeCropRect(start, "nw", -100, -100, bounds),
        { x: 0, y: 0, width: 140, height: 100 }
    );
});

test("crop rectangle maps to source pixels for portrait and landscape images", () => {
    assert.deepEqual(
        mapCropRectToSource(
            { x: 10, y: 20, width: 100, height: 80 },
            { width: 200, height: 160 },
            1000,
            800
        ),
        { x: 50, y: 100, width: 500, height: 400 }
    );
    assert.deepEqual(
        mapCropRectToSource(
            { x: 20, y: 10, width: 100, height: 50 },
            { width: 200, height: 100 },
            1200,
            600
        ),
        { x: 120, y: 60, width: 600, height: 300 }
    );
});

test("JPEG export preserves crop dimensions and draws the source crop without distortion", async () => {
    let drawArguments;
    const source = { naturalWidth: 1200, naturalHeight: 800 };
    const blob = await exportSignatureCrop(
        source,
        { x: 10, y: 20, width: 100, height: 80 },
        { width: 200, height: 160 },
        {
            createCanvas: () => ({
                getContext: () => ({
                    drawImage: (...args) => { drawArguments = args; }
                }),
                toBlob: (callback, type) => callback(new Blob(["jpeg"], { type }))
            })
        }
    );

    assert.equal(blob.type, "image/jpeg");
    assert.deepEqual(drawArguments.slice(1), [60, 100, 600, 400, 0, 0, 600, 400]);
});

test("JPEG export reduces quality to fit the 2 MB limit, then rejects oversized output", async () => {
    const qualities = [];
    const canvas = {
        getContext: () => ({ drawImage() {} }),
        toBlob(callback, type, quality) {
            qualities.push(quality);
            callback(new Blob(["x".repeat(quality > 0.8 ? 2_100_000 : 100)], { type }));
        }
    };
    const source = { naturalWidth: 100, naturalHeight: 80 };
    const args = [source, { x: 0, y: 0, width: 100, height: 80 }, { width: 100, height: 80 }];
    const blob = await exportSignatureCrop(...args, { createCanvas: () => canvas });
    assert.ok(blob.size <= 2 * 1024 * 1024);
    assert.deepEqual(qualities, [0.92, 0.88, 0.82, 0.76]);

    await assert.rejects(
        exportSignatureCrop(...args, {
            maxBytes: 5,
            createCanvas: () => ({
                getContext: () => ({ drawImage() {} }),
                toBlob(callback, type) { callback(new Blob(["oversized"], { type })); }
            })
        }),
        /Adjust the crop or retake/
    );
});

test("invalid crop bounds are rejected", () => {
    assert.throws(() => constrainCropRect({ x: 0, y: 0, width: 1, height: 1 }, { width: 0, height: 10 }));
});

test("registration signature flow uses camera capture and applicant-controlled pointer crop", async () => {
    const camera = await readFile(new URL("../../static/js/registration/signature-camera.js", import.meta.url), "utf8");
    const template = await readFile(new URL("../../templates/registration/registration.html", import.meta.url), "utf8");

    assert.match(camera, /facingMode:\s*\{\s*ideal:\s*"environment"/);
    assert.match(camera, /addEventListener\("pointerdown"/);
    assert.match(camera, /addEventListener\("pointermove"/);
    assert.match(camera, /resizeCropRect\(/);
    assert.match(camera, /input\.files\s*=\s*transfer\.files/);
    assert.match(camera, /cropEditing\s*\|\|\s*!signatureConfirmed/);
    assert.doesNotMatch(camera, /detectInk|connectedComponent|floodFill/);
    assert.match(template, /accept="image\/jpeg" hidden/);
    assert.match(template, /Drag the box to move it\. Drag a handle to resize it/);
});
