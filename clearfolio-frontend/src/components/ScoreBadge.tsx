"use client";

import { useEffect, useRef } from "react";
import { Grade, gradeColour } from "@/types/audit";

interface ScoreBadgeProps {
  score: number;
  grade: Grade;
  size?:  number;
}

export default function ScoreBadge({ score, grade, size = 120 }: ScoreBadgeProps) {
  const fillRef = useRef<SVGCircleElement>(null);
  const colour  = gradeColour(grade);

  const radius      = 44;
  const circumference = 2 * Math.PI * radius;
  const offset      = circumference - (score / 100) * circumference;

  useEffect(() => {
    const el = fillRef.current;
    if (!el) return;

    // Start from empty, then animate to correct offset
    el.style.strokeDasharray  = `${circumference}`;
    el.style.strokeDashoffset = `${circumference}`;
    el.style.stroke           = colour;

    // Trigger animation on next frame
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (el) el.style.strokeDashoffset = `${offset}`;
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [score, colour, circumference, offset]);

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      {/* SVG Ring */}
      <svg
        className="score-ring absolute inset-0"
        width={size}
        height={size}
        viewBox="0 0 100 100"
      >
        {/* Track */}
        <circle
          className="track"
          cx="50" cy="50"
          r={radius}
        />
        {/* Animated fill */}
        <circle
          ref={fillRef}
          className="fill"
          cx="50" cy="50"
          r={radius}
          style={{
            strokeDasharray:  circumference,
            strokeDashoffset: circumference,
            stroke:           colour,
            transition:       "stroke-dashoffset 1.4s cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        />
      </svg>

      {/* Inner content */}
      <div className="relative flex flex-col items-center leading-none">
        <span
          className="font-mono font-semibold"
          style={{
            fontSize:   size * 0.275,
            color:      colour,
            lineHeight: 1,
          }}
        >
          {score}
        </span>
        <span
          className="font-heading font-700 tracking-tight mt-0.5"
          style={{
            fontSize:  size * 0.13,
            color:     colour,
            opacity:   0.7,
          }}
        >
          Grade {grade}
        </span>
      </div>
    </div>
  );
}
