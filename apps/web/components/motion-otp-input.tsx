"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";
import * as React from "react";

import { DURATION, EASING, MOTION_VARIANTS, SPRING } from "@/lib/motion";

interface MotionOtpInputProps {
  value: string;
  onChange: (val: string) => void;
  onComplete?: (code: string) => void;
  hasError?: boolean;
  isSuccess?: boolean;
  disabled?: boolean;
  id?: string;
}

export function MotionOtpInput({
  value,
  onChange,
  onComplete,
  hasError = false,
  isSuccess = false,
  disabled = false,
  id = "otp-input",
}: MotionOtpInputProps) {
  const inputsRef = React.useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: 6 }, (_, i) => value[i] || "");

  const handleDigitChange = (index: number, char: string) => {
    const clean = char.replace(/\D/g, "");
    if (!clean) {
      // Clear current digit
      const next = digits.map((d, i) => (i === index ? "" : d)).join("");
      onChange(next);
      return;
    }

    // Single digit entry
    const newDigit = clean.slice(-1);
    const updated = [...digits];
    updated[index] = newDigit;
    const nextVal = updated.join("");
    onChange(nextVal);

    if (nextVal.length === 6 && onComplete) {
      onComplete(nextVal);
    } else if (index < 5) {
      // Auto-advance
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      if (!digits[index] && index > 0) {
        inputsRef.current[index - 1]?.focus();
        const updated = [...digits];
        updated[index - 1] = "";
        onChange(updated.join(""));
      } else {
        const updated = [...digits];
        updated[index] = "";
        onChange(updated.join(""));
      }
    } else if (e.key === "ArrowLeft" && index > 0) {
      inputsRef.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < 5) {
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;

    onChange(pasted);
    const targetIndex = Math.min(pasted.length, 5);
    inputsRef.current[targetIndex]?.focus();

    if (pasted.length === 6 && onComplete) {
      onComplete(pasted);
    }
  };

  return (
    <motion.div
      variants={MOTION_VARIANTS.shakeError}
      animate={hasError ? "shake" : "default"}
      className="flex flex-col items-center gap-2"
    >
      <div className="flex items-center justify-center gap-2 sm:gap-2.5">
        {Array.from({ length: 6 }).map((_, i) => {
          const isFilled = Boolean(digits[i]);
          return (
            <motion.div
              key={i}
              initial={false}
              animate={
                isSuccess
                  ? { scale: [1, 1.08, 1], borderColor: "#FFD400" }
                  : hasError
                  ? { borderColor: "#FF334B" }
                  : isFilled
                  ? { scale: [1, 1.05, 1], borderColor: "#FFD400" }
                  : { scale: 1 }
              }
              transition={SPRING.snappy}
              className="relative"
            >
              <input
                ref={(el) => {
                  inputsRef.current[i] = el;
                }}
                id={i === 0 ? id : `${id}-${i}`}
                data-testid={`otp-box-${i}`}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={1}
                disabled={disabled || isSuccess}
                value={digits[i] || ""}
                onChange={(e) => handleDigitChange(i, e.target.value)}
                onKeyDown={(e) => handleKeyDown(i, e)}
                onPaste={handlePaste}
                onFocus={(e) => e.target.select()}
                className={`h-12 w-10 sm:h-14 sm:w-12 rounded-xl border text-center font-mono text-xl sm:text-2xl font-bold transition-all duration-150 focus:outline-none select-none shadow-sm ${
                  isSuccess
                    ? "border-primary/80 bg-primary/10 text-primary shadow-primary-glow"
                    : hasError
                    ? "border-danger/80 bg-danger/10 text-danger shadow-sm shadow-danger/30"
                    : isFilled
                    ? "border-primary/60 bg-surface-raised text-foreground shadow-sm shadow-primary/20"
                    : "border-border/80 bg-surface/80 text-foreground hover:border-border focus:border-primary focus:bg-surface focus:ring-2 focus:ring-primary/40"
                }`}
                aria-label={`Digit ${i + 1} of 6`}
              />
              {/* Subtle gold specular dot at top of active box */}
              {isFilled && (
                <span className="pointer-events-none absolute left-1/2 top-1.5 h-1 w-1 -translate-x-1/2 rounded-full bg-primary/70" />
              )}
            </motion.div>
          );
        })}
      </div>

      {isSuccess && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={SPRING.bouncy}
          className="flex items-center gap-1.5 text-xs font-semibold text-primary"
        >
          <Check className="h-4 w-4" />
          <span>Code Verified</span>
        </motion.div>
      )}
    </motion.div>
  );
}
