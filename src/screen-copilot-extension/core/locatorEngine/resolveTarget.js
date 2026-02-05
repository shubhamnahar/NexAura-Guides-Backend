import { collectFrames } from "./frameScanner.js";
import { waitForDomStable } from "./waitForDomStable.js";
import {
  queryByCss,
  queryById,
  queryByRole,
  queryByText,
} from "./locatorStrategies.js";
import { scoreCandidate } from "./scoreMatch.js";
import { visionFindElement } from "../vision/visionFallback.js";
import { findTargetElement } from "./hybridSelector.js";

const DEFAULT_TIMEOUT = 8000;
const DEFAULT_RETRIES = 3;

export async function resolveTarget(stepTarget, options = {}) {
  const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT;
  const retries = options.retries ?? DEFAULT_RETRIES;
  const start = Date.now();
  let attempt = 0;
  let lastError = null;
  const debug = [];

  while (attempt <= retries) {
    const remaining = timeoutMs - (Date.now() - start);
    if (remaining <= 0) break;
    try {
      const res = await attemptResolve(stepTarget, remaining, debug);
      if (res) return { status: "SUCCESS", element: res.el, frame: res.frame, debug };
    } catch (e) {
      lastError = e;
      debug.push({ type: "error", message: e?.message });
    }
    attempt++;
    await wait(200 * attempt);
  }
  return {
    status: "HARD_FAIL",
    element: null,
    frame: null,
    debug,
    error: lastError ? String(lastError) : "Unable to resolve target",
  };
}

async function attemptResolve(stepTarget, timeoutMs, debug) {
  const timer = createTimeout(timeoutMs, "resolveTarget timeout");
  try {
    await waitForDomStable({ timeoutMs: Math.min(timeoutMs, 1500) });
    const frames = collectFrames();
    for (const frame of frames) {
      const res = resolveInFrame(frame, stepTarget, debug);
      if (res) {
        timer.clear();
        return res;
      }
    }
  } finally {
    timer.clear();
  }
  return null;
}

function resolveInFrame(frame, target, debug) {
  const win = frame.win;
  const candidates = [];
  const locators = Array.isArray(target.preferredLocators)
    ? target.preferredLocators
    : [];

  const pushCandidates = (list, why) => {
    list.forEach((el) => {
      const score = scoreCandidate({ el, target });
      candidates.push({ el, score, why });
    });
  };

  // Primary attempt: hybrid selector scoring based on fingerprint
  if (target.hybridFingerprint) {
    const el = findTargetElement(target.hybridFingerprint, {
      root: win.document,
      threshold: 60,
    });
    if (el) {
      candidates.push({ el, score: 100, why: "hybridSelector" });
      return { el, frame };
    }
  }

  for (const loc of locators) {
    if (!loc || !loc.type) continue;
    if (loc.type === "id") {
      pushCandidates(queryById(win, loc.value), "id");
    } else if (loc.type === "css") {
      pushCandidates(queryByCss(win, loc.value), "css");
    } else if (loc.type === "role") {
      pushCandidates(queryByRole(win, loc.role || loc.value, loc.name), "role");
    } else if (loc.type === "text") {
      pushCandidates(queryByText(win, loc.value, loc.tag), "text");
    } else if (loc.type === "xpath") {
      const nodes = queryByXPath(win, loc.value);
      pushCandidates(nodes, "xpath");
    }
  }

  if (!candidates.length && target.context?.ancestorTrail?.length) {
    try {
      const anchor = findAncestorAnchor(win, target.context.ancestorTrail);
      if (anchor) {
        const sub = anchor.querySelectorAll(target.fingerprint.tag || "*");
        pushCandidates(Array.from(sub), "ancestorTrail");
      }
    } catch (e) {
      debug.push({ type: "warn", message: "ancestor search failed" });
    }
  }

  if (!candidates.length && target.fingerprint?.text) {
    pushCandidates(queryByText(win, target.fingerprint.text), "fingerprint-text");
  }

  if (!candidates.length) return null;
  candidates.sort((a, b) => b.score - a.score);
  const top = candidates[0];
  if (!top || !top.el) return null;
  return { el: top.el, frame };
}

function queryByXPath(win, xpath) {
  if (!xpath) return [];
  try {
    const doc = win.document;
    const res = doc.evaluate(xpath, doc, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    const out = [];
    for (let i = 0; i < res.snapshotLength; i++) {
      const node = res.snapshotItem(i);
      if (node instanceof win.Element) out.push(node);
    }
    return out;
  } catch (e) {
    return [];
  }
}

function findAncestorAnchor(win, trail) {
  if (!Array.isArray(trail) || !trail.length) return null;
  let current = win.document.body;
  for (const seg of trail) {
    if (!current) break;
    const children = current.children;
    const idx = Math.min(seg.index || 0, children.length - 1);
    current = children[idx];
  }
  return current;
}

function wait(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

function createTimeout(ms, label) {
  const id = setTimeout(() => {
    console.warn(label || "timeout");
  }, ms);
  return { clear: () => clearTimeout(id) };
}
