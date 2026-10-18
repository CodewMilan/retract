import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";

gsap.registerPlugin(useGSAP, DrawSVGPlugin, ScrambleTextPlugin);

export const MOTION_OK = "(prefers-reduced-motion: no-preference)";

export { gsap, useGSAP };
