const PATTERN = [
  "#8ec0ee", "#fff6ee", "#f7d0dc", "#7eb6ea",
  "#e2e9f3", "#ff7a12", "#ff4500", "#f4d94a",
  "#1c2430", "#ff5a1a", "#141210", "#ff8f2a",
];
const REDUCED = "(prefers-reduced-motion: reduce)";
let loadingGsap;

function loadGsap() {
  if (window.gsap) return Promise.resolve(window.gsap);
  if (loadingGsap) return loadingGsap;
  loadingGsap = new Promise((resolve, reject) => {
    const element = document.createElement("script");
    element.src = "/assets/gsap.min.js";
    element.async = true;
    element.onload = () => resolve(window.gsap);
    element.onerror = () => reject(new Error("Loader motion unavailable"));
    document.head.append(element);
  });
  return loadingGsap;
}

export function paintWait(host, {gsap: gsapLib, label = "", compact = false, brand = false, quiet = false} = {}) {
  if (!host) return () => {};
  host.replaceChildren();
  const root = document.createElement("div");
  root.className = compact ? "wait wait--compact" : "wait";
  if (label) root.setAttribute("aria-label", label);
  if (brand) {
    const mark = document.createElement("span");
    mark.className = "brand-name";
    mark.textContent = "Retract";
    root.append(mark);
  }
  const grid = document.createElement("div");
  grid.className = "wait-grid";
  grid.setAttribute("aria-hidden", "true");
  const cells = PATTERN.map(color => {
    const cell = document.createElement("span");
    cell.style.background = color;
    grid.append(cell);
    return cell;
  });
  root.append(grid);
  if (label && !quiet) {
    const text = document.createElement("p");
    text.className = "wait-label";
    text.textContent = label;
    root.append(text);
  }
  host.append(root);
  let tween;
  const motion = gsapLib || null;
  const animate = gsap => {
    if (!gsap || window.matchMedia(REDUCED).matches || !root.isConnected) return;
    tween = gsap.timeline({
      repeat: -1,
      yoyo: true,
      repeatDelay: 0.12,
      onRepeat() { if (!root.isConnected) this.kill(); },
    });
    tween.fromTo(cells, {autoAlpha: 0.28, scale: 0.72}, {
      autoAlpha: 1,
      scale: 1,
      duration: 0.55,
      ease: "power2.inOut",
      stagger: {each: 0.045, from: "center", grid: [3, 4]},
    });
  };
  if (motion) animate(motion);
  else loadGsap().then(animate).catch(() => {});
  return () => tween?.kill();
}
