import { normalizeText } from "../guideSchema.js";
import { generateElementFingerprint } from "../locatorEngine/hybridSelector.js";

export function captureTarget(element, frameInfo = {}) {
  if (!(element instanceof Element)) return null;
  const locatorList = [];

  const id = element.id;
  if (id) locatorList.push({ type: "id", value: id, confidence: 0.9 });

  const dataTest = element.getAttribute("data-testid") || element.getAttribute("data-test");
  if (dataTest) locatorList.push({ type: "css", value: `[data-testid="${dataTest}"]`, confidence: 0.85 });

  const ariaLabel = element.getAttribute("aria-label");
  const role = element.getAttribute("role");
  if (role) locatorList.push({ type: "role", role, name: ariaLabel || "", confidence: 0.7 });

  const cssPath = buildCssPath(element);
  if (cssPath) locatorList.push({ type: "css", value: cssPath, confidence: 0.5 });

  const xpath = buildXPath(element);
  if (xpath) locatorList.push({ type: "xpath", value: xpath, confidence: 0.4 });

  const text = normalizeText(element.innerText || element.textContent || "");
  if (text) locatorList.push({ type: "text", value: text, tag: element.tagName.toLowerCase(), confidence: 0.4 });

  const ancestorTrail = buildAncestorTrail(element);
  const siblingIndex = computeSiblingIndex(element);

  const fingerprint = {
    tag: element.tagName.toLowerCase(),
    role: role || null,
    ariaLabel: ariaLabel || null,
    text: text || null,
    attrs: collectAttrs(element),
    classTokens: Array.from(element.classList || []),
  };

  return {
    preferredLocators: locatorList,
    fingerprint,
    hybridFingerprint: generateElementFingerprint(element),
    context: {
      ancestorTrail,
      siblingIndex,
      nearbyAnchors: collectNearbyAnchors(element),
      frame: frameInfo,
    },
    vision: {
      templateId: null,
      bbox: readBBox(element),
    },
    history: {
      lastSuccessfulLocator: null,
      successCounts: {},
    },
  };
}

function buildCssPath(el) {
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && parts.length < 5) {
    let part = node.tagName.toLowerCase();
    if (node.id) {
      part = `${part}#${node.id}`;
      parts.unshift(part);
      break;
    }
    if (node.classList.length) {
      part += "." + Array.from(node.classList).slice(0, 2).join(".");
    }
    parts.unshift(part);
    node = node.parentElement;
  }
  return parts.join(" > ");
}

function buildXPath(el) {
  if (!el || el.nodeType !== 1) return "";
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && parts.length < 5) {
    let idx = 1;
    let sib = node.previousSibling;
    while (sib) {
      if (sib.nodeType === 1 && sib.nodeName === node.nodeName) idx++;
      sib = sib.previousSibling;
    }
    parts.unshift(`${node.nodeName}[${idx}]`);
    node = node.parentNode;
  }
  return "/" + parts.join("/");
}

function buildAncestorTrail(el) {
  const trail = [];
  let node = el.parentElement;
  while (node && trail.length < 4) {
    trail.unshift({
      tag: node.tagName.toLowerCase(),
      index: computeSiblingIndex(node),
    });
    node = node.parentElement;
  }
  return trail;
}

function computeSiblingIndex(el) {
  if (!el || !el.parentElement) return 0;
  const siblings = Array.from(el.parentElement.children).filter(
    (n) => n.tagName === el.tagName
  );
  return siblings.indexOf(el);
}

function collectAttrs(el) {
  const attrs = {};
  for (const attr of el.attributes) {
    if (!attr.name.startsWith("data-") && attr.name !== "id") continue;
    attrs[attr.name] = attr.value;
  }
  return attrs;
}

function collectNearbyAnchors(el) {
  const anchors = [];
  const siblings = el.parentElement ? Array.from(el.parentElement.children) : [];
  siblings.slice(0, 6).forEach((sib, idx) => {
    if (!(sib instanceof Element) || sib === el) return;
    anchors.push({
      tag: sib.tagName.toLowerCase(),
      text: normalizeText(sib.textContent || ""),
      offset: idx,
    });
  });
  return anchors;
}

function readBBox(el) {
  const r = el.getBoundingClientRect();
  return { x: r.x, y: r.y, width: r.width, height: r.height };
}
