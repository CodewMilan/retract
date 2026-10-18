import { useEffect, useRef, useState } from "react";

export function SplitWords({ text, align = "left" }) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      node.setAttribute("animate", "animate");
      observer.unobserve(node);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <span className="is-visually-hidden">{text}</span>
      <span className="split-words" ref={ref} aria-hidden="true" data-align={align}>
        {text.split(" ").map((word, index) => (
          <span key={index}>{word}</span>
        ))}
      </span>
    </>
  );
}

const plain = new Intl.NumberFormat("en-US", { useGrouping: true });

function padded(value) {
  const digits = Math.max(1, String(Math.abs(value)).length);
  return new Intl.NumberFormat("en-US", { useGrouping: true, minimumIntegerDigits: digits });
}

export function AutoIncrementValue({ value, index = 0, hidden = false }) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    node.textContent = padded(value).format(0);
    let frame = 0;
    let timer = 0;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        const format = padded(value);
        let start = 0;
        const step = (now) => {
          if (!start) start = now;
          const t = Math.min((now - start) / 500, 1);
          const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
          node.textContent = format.format(Math.round(eased * value));
          if (t < 1) frame = requestAnimationFrame(step);
          else node.textContent = plain.format(value);
        };
        const delay = 30 * index;
        if (delay > 0) timer = setTimeout(() => (frame = requestAnimationFrame(step)), delay);
        else frame = requestAnimationFrame(step);
      },
      { rootMargin: "-25% 0px -25% 0px" },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      clearTimeout(timer);
      cancelAnimationFrame(frame);
    };
  }, [value, index]);

  const label = plain.format(value);
  if (!hidden) return <span ref={ref}>{label}</span>;
  return (
    <>
      <span ref={ref} aria-hidden="true">{label}</span>
      <span className="is-visually-hidden">{label}</span>
    </>
  );
}

export function useInView(ref, amount = 0.35) {
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      threshold: amount,
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref, amount]);

  return inView;
}

export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}
