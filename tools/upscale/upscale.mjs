/**
 * Upscale / enhance tarot card crops via Firebase AI Logic (Gemini image model).
 *
 * Setup:
 *   cp firebase-config.example.json firebase-config.json   # fill projectId + appId
 *   npm install
 *
 * Use:
 *   node upscale.mjs --only major_00      # single card (test fidelity first!)
 *   node upscale.mjs --all --resume       # all 78, skip ones already done
 *
 * Input : ../../images-final/_crops/<id>.png   (the clean named crops)
 * Output: ../../images-final-hq/<id>.png
 */
import { initializeApp } from "firebase/app";
import {
  getVertexAI,
  getGenerativeModel,
  HarmBlockThreshold,
  HarmCategory,
} from "firebase/vertexai";
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "..", "images-final", "_crops");
const OUT = join(HERE, "..", "..", "images-final-hq");

const MODEL = "gemini-3.1-flash-image"; // nano banana 2

// Keep the artwork identical — only improve resolution/clarity. The card art and the
// Ukrainian label must stay exactly the same; this is a restore/upscale, not a redraw.
const PROMPT =
  "Upscale and restore this tarot card illustration to crisp high resolution. " +
  "Keep the EXACT same artwork: same cat character, pose, composition, colors, border " +
  "and the Ukrainian text label at the bottom unchanged. Do not redraw, do not add or " +
  "remove elements. Only sharpen, denoise and increase detail. Output the full card image, " +
  "same aspect ratio.";

function loadModel() {
  const cfgPath = join(HERE, "firebase-config.json");
  if (!existsSync(cfgPath)) {
    console.error("Missing firebase-config.json (copy the .example and fill projectId + appId).");
    process.exit(1);
  }
  const cfg = JSON.parse(readFileSync(cfgPath, "utf8"));
  const app = initializeApp(cfg);
  const vertexAI = getVertexAI(app, { location: "global" });
  const off = (category) => ({ category, threshold: HarmBlockThreshold.OFF });
  return getGenerativeModel(vertexAI, {
    model: MODEL,
    generationConfig: { temperature: 1, topP: 0.95, maxOutputTokens: 32768 },
    safetySettings: [
      off(HarmCategory.HARM_CATEGORY_HATE_SPEECH),
      off(HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT),
      off(HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT),
      off(HarmCategory.HARM_CATEGORY_HARASSMENT),
    ],
  });
}

async function enhance(model, id) {
  const inPath = join(SRC, `${id}.png`);
  const data = readFileSync(inPath).toString("base64");
  const result = await model.generateContent([
    PROMPT,
    { inlineData: { mimeType: "image/png", data } },
  ]);
  const parts = result.response.candidates?.[0]?.content?.parts || [];
  const imgPart = parts.find((p) => p.inlineData);
  if (!imgPart) {
    const txt = parts.map((p) => p.text).filter(Boolean).join(" ");
    throw new Error(`no image returned for ${id}. Model said: ${txt.slice(0, 200)}`);
  }
  writeFileSync(join(OUT, `${id}.png`), Buffer.from(imgPart.inlineData.data, "base64"));
}

async function main() {
  const args = process.argv.slice(2);
  const only = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
  const resume = args.includes("--resume");

  mkdirSync(OUT, { recursive: true });
  const model = loadModel();

  let ids;
  if (only) ids = [only];
  else ids = readdirSync(SRC).filter((f) => f.endsWith(".png")).map((f) => f.replace(".png", ""));

  let done = 0;
  for (const id of ids) {
    if (resume && existsSync(join(OUT, `${id}.png`))) {
      console.log(`skip ${id} (exists)`);
      continue;
    }
    try {
      process.stdout.write(`enhancing ${id} ... `);
      await enhance(model, id);
      console.log("ok");
      done++;
      await new Promise((r) => setTimeout(r, 1500)); // gentle pacing
    } catch (e) {
      console.log(`FAIL: ${e.message}`);
    }
  }
  console.log(`\ndone: ${done}/${ids.length} -> ${OUT}`);
}

main();
