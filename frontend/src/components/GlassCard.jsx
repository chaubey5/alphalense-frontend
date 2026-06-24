import { useRef } from "react";
import { motion } from "framer-motion";

export default function GlassCard({ children, className = "", glow = "", eyebrow, title, testId }) {
  const ref = useRef(null);

  const onMove = (e) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(1400px) rotateX(${-py * 4}deg) rotateY(${px * 5}deg)`;
  };
  const reset = () => { if (ref.current) ref.current.style.transform = ""; };

  return (
    <motion.div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={reset}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.2, 0.7, 0.2, 1] }}
      className={`glass p-6 transition-transform duration-300 ${glow} ${className}`}
      style={{ transformStyle: "preserve-3d" }}
      data-testid={testId}
    >
      {(eyebrow || title) && (
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <div>
            {eyebrow && <div className="label-eyebrow mb-1">{eyebrow}</div>}
            {title && <div className="text-base font-medium text-[var(--text)]">{title}</div>}
          </div>
        </div>
      )}
      {children}
    </motion.div>
  );
}
