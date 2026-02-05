// Hybrid selector: tag-first filtering with weighted scoring across text, context, visuals, and class.

// Normalize visible text for stable comparisons
const cleanText = (str) => (str || "").replace(/\s+/g, " ").trim();

// Parse "rgb/rgba(...)" into numeric channels
const parseRGB = (cssColor = "") => {
  const m = cssColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
  return m ? { r: +m[1], g: +m[2], b: +m[3] } : { r: 0, g: 0, b: 0 };
};

// Percentage difference between two numbers
const pctDiff = (a, b) => (a === 0 && b === 0 ? 0 : Math.abs(a - b) / Math.max(a, b));

/**
 * Capture a robust fingerprint for a clicked element.
 * Keeps basic info, visible text, nearby context, and key computed styles.
 */
export function generateElementFingerprint(element) {
  if (!element) return null;

  const tagName = element.tagName?.toLowerCase() || "";
  const id = element.id || "";
  const className = element.className?.toString() || "";

  const textAnchor = cleanText(element.innerText);
  const parentText = cleanText(element.parentElement?.innerText);
  const prevText = cleanText(element.previousElementSibling?.innerText);
  // Inputs often lack innerText; fall back to nearby text so we have an anchor.
  const contextText = textAnchor ? "" : prevText || parentText || "";

  const styles = element.ownerDocument.defaultView.getComputedStyle(element);
  const visuals = {
    backgroundColor: styles.backgroundColor,
    color: styles.color,
    width: parseFloat(styles.width),
    height: parseFloat(styles.height),
  };

  return {
    tagName,
    id,
    className,
    textAnchor,
    contextText,
    visuals,
  };
}

/**
 * Find the best-matching element on the current page using the stored fingerprint.
 * Uses a weighted score:
 *  - +40 exact text match
 *  - +25 matching nearby context (parent/previous sibling text)
 *  - +20 visual similarity (bg color + size within 10%)
 *  - +15 matching className
 */
export function findTargetElement(fingerprint, { root = document, threshold = 60 } = {}) {
  if (!fingerprint?.tagName) return null;

  const doc = root; // either the document or a shadow root like frame document
  const win = doc.defaultView || window;
  const candidates = Array.from(doc.querySelectorAll(fingerprint.tagName));

  let best = { el: null, score: 0 };

  for (const el of candidates) {
    if (!(el instanceof win.Element)) continue;
    let score = 0;

    const text = cleanText(el.innerText);
    if (fingerprint.textAnchor && text === fingerprint.textAnchor) {
      score += 40; // Exact text match
    }

    // Context scoring helps for inputs/labels without innerText
    const parentText = cleanText(el.parentElement?.innerText);
    const prevText = cleanText(el.previousElementSibling?.innerText);
    if (
      fingerprint.contextText &&
      (parentText === fingerprint.contextText || prevText === fingerprint.contextText)
    ) {
      score += 25;
    }

    // Visual similarity: background color + dimensions within 10% tolerance
    if (fingerprint.visuals) {
      const styles = win.getComputedStyle(el);
      const bg = parseRGB(styles.backgroundColor);
      const targetBg = parseRGB(fingerprint.visuals.backgroundColor);
      const colorDelta =
        (Math.abs(bg.r - targetBg.r) + Math.abs(bg.g - targetBg.g) + Math.abs(bg.b - targetBg.b)) /
        (3 * 255);
      const widthDelta = pctDiff(parseFloat(styles.width), fingerprint.visuals.width);
      const heightDelta = pctDiff(parseFloat(styles.height), fingerprint.visuals.height);

      if (colorDelta <= 0.1 && widthDelta <= 0.1 && heightDelta <= 0.1) {
        score += 20;
      }
    }

    // Class string match (simple but stable enough for many UIs)
    if (fingerprint.className && el.className?.toString() === fingerprint.className) {
      score += 15;
    }

    if (score > best.score) best = { el, score };
  }

  return best.score >= threshold ? best.el : null;
}
