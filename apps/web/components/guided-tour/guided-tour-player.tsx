"use client";

import React, { useEffect, useState } from "react";
import { useGuidedTour } from "./guided-tour-context";
import { Button, Badge } from "@jkr/ui";
import {
  Volume2,
  VolumeX,
  Play,
  Pause,
  SkipForward,
  SkipBack,
  X,
  Sparkles,
  Languages,
  Headphones,
  Radio,
} from "lucide-react";
import { TourLanguage } from "@/lib/guided-tour-scripts";

export function GuidedTourPlayer() {
  const {
    isOpen,
    currentStepIndex,
    isPlaying,
    language,
    activeProvider,
    isLoadingAudio,
    currentTour,
    currentStep,
    totalSteps,
    stopTour,
    pauseTour,
    resumeTour,
    nextStep,
    prevStep,
    goToStep,
    setLanguage,
  } = useGuidedTour();

  const [highlightStyle, setHighlightStyle] = useState<React.CSSProperties | null>(null);

  // Calculate position of the active target element for the spotlight glow
  useEffect(() => {
    if (!isOpen || !currentStep) {
      setHighlightStyle(null);
      return;
    }

    const updatePosition = () => {
      const el = document.getElementById(currentStep.id);
      if (!el) {
        setHighlightStyle(null);
        return;
      }

      const rect = el.getBoundingClientRect();
      setHighlightStyle({
        top: `${rect.top + window.scrollY - 8}px`,
        left: `${rect.left + window.scrollX - 8}px`,
        width: `${rect.width + 16}px`,
        height: `${rect.height + 16}px`,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition);

    const timer = setTimeout(updatePosition, 300);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition);
      clearTimeout(timer);
    };
  }, [isOpen, currentStep, currentStepIndex]);

  if (!isOpen || !currentStep || !currentTour) return null;

  const currentTitle = currentStep.title[language] || currentStep.title["en-IN"];
  const currentNarration = currentStep.narration[language] || currentStep.narration["en-IN"];

  return (
    <>
      {/* Target Element Spotlight Glow Overlay */}
      {highlightStyle && (
        <div
          style={highlightStyle}
          className="pointer-events-none fixed z-40 rounded-2xl border-2 border-primary ring-4 ring-primary/30 ring-offset-4 ring-offset-background shadow-[0_0_40px_rgba(124,92,255,0.4)] transition-all duration-500 animate-pulse"
        >
          <div className="absolute -top-3.5 left-4 flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[#7C5CFF] to-[#5B3FE4] px-3 py-0.5 text-[11px] font-semibold text-white shadow-md">
            <Sparkles className="h-3 w-3 text-amber-300" />
            <span>{currentStep.highlightName}</span>
          </div>
        </div>
      )}

      {/* Floating Guided Tour Control Player */}
      <div className="fixed bottom-6 right-6 z-50 w-full max-w-md animate-in fade-in slide-in-from-bottom-5 duration-300">
        <div className="overflow-hidden rounded-2xl border border-primary/40 bg-surface/95 p-4 shadow-2xl backdrop-blur-xl">
          {/* Header Bar */}
          <div className="flex items-center justify-between border-b border-border/60 pb-3">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#5B3FE4] text-white shadow-md shadow-primary/30">
                <Headphones className="h-4 w-4" />
              </div>
              <div>
                <h4 className="flex items-center gap-1.5 font-display text-sm font-bold text-foreground">
                  <span>AI Voice Tour</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-secondary/15 px-2 py-0.5 text-[10px] font-semibold text-secondary">
                    <Radio className="h-2.5 w-2.5 animate-pulse" />
                    Live Demo
                  </span>
                </h4>
                <p className="text-[11px] text-muted-foreground">
                  {currentTour.pageTitle} · Step {currentStepIndex + 1} of {totalSteps}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              {/* Voice Provider Badge */}
              <Badge
                variant="outline"
                className="hidden sm:inline-flex text-[10px] border-primary/30 text-primary bg-primary/10"
              >
                {activeProvider === "sarvam" ? "Sarvam Bulbul (Priya)" : "Browser Speech"}
              </Badge>

              {/* Close Tour Button */}
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                onClick={stopTour}
                title="Exit tour"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Narration Body */}
          <div className="my-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">{currentTitle}</span>

              {/* Multilingual Selector */}
              <div className="flex items-center gap-1 rounded-lg border border-border/80 bg-surface-raised p-0.5 text-[10px]">
                <Languages className="h-3 w-3 text-muted-foreground ml-1" />
                <button
                  type="button"
                  onClick={() => setLanguage("en-IN")}
                  className={`rounded px-1.5 py-0.5 transition-all ${
                    language === "en-IN"
                      ? "bg-primary text-white font-medium shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLanguage("te-IN")}
                  className={`rounded px-1.5 py-0.5 transition-all ${
                    language === "te-IN"
                      ? "bg-primary text-white font-medium shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  తెలుగు
                </button>
                <button
                  type="button"
                  onClick={() => setLanguage("hi-IN")}
                  className={`rounded px-1.5 py-0.5 transition-all ${
                    language === "hi-IN"
                      ? "bg-primary text-white font-medium shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  हिन्दी
                </button>
              </div>
            </div>

            {/* Narration Subtitle Box */}
            <div className="relative rounded-xl border border-border/60 bg-surface/80 p-3">
              <p className="text-xs leading-relaxed text-foreground/90 font-sans italic">
                &ldquo;{currentNarration}&rdquo;
              </p>

              {/* Audio Wave Visualizer while playing */}
              <div className="mt-2.5 flex items-center justify-between pt-1 border-t border-border/40">
                <div className="flex items-center gap-1 h-3.5">
                  {isPlaying ? (
                    <>
                      <span className="w-1 bg-secondary rounded-full animate-wave-1 h-3" />
                      <span className="w-1 bg-secondary rounded-full animate-wave-2 h-3.5" />
                      <span className="w-1 bg-secondary rounded-full animate-wave-3 h-2" />
                      <span className="w-1 bg-secondary rounded-full animate-wave-4 h-3" />
                      <span className="w-1 bg-secondary rounded-full animate-wave-2 h-2.5" />
                      <span className="ml-1.5 text-[10px] text-secondary font-medium">Speaking narration...</span>
                    </>
                  ) : (
                    <span className="text-[10px] text-muted-foreground">Paused</span>
                  )}
                </div>

                {isLoadingAudio && (
                  <span className="text-[10px] text-primary animate-pulse">Generating voice...</span>
                )}
              </div>
            </div>
          </div>

          {/* Player Controls & Step Dots */}
          <div className="flex items-center justify-between pt-1">
            {/* Step Dots */}
            <div className="flex items-center gap-1.5">
              {currentTour.steps.map((s, idx) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => goToStep(idx)}
                  className={`h-2 rounded-full transition-all duration-300 ${
                    idx === currentStepIndex
                      ? "w-6 bg-gradient-to-r from-primary to-[#5B3FE4]"
                      : "w-2 bg-border hover:bg-muted-foreground/50"
                  }`}
                  title={`Go to step ${idx + 1}`}
                />
              ))}
            </div>

            {/* Playback Buttons */}
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="h-8 px-2.5 text-xs gap-1"
                disabled={currentStepIndex === 0}
                onClick={prevStep}
              >
                <SkipBack className="h-3.5 w-3.5" />
                <span>Prev</span>
              </Button>

              {isPlaying ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 px-3 text-xs gap-1 border-primary/40 text-primary hover:bg-primary/10"
                  onClick={pauseTour}
                >
                  <Pause className="h-3.5 w-3.5" />
                  <span>Pause</span>
                </Button>
              ) : (
                <Button
                  variant="gradient"
                  size="sm"
                  className="h-8 px-3 text-xs gap-1"
                  onClick={resumeTour}
                >
                  <Play className="h-3.5 w-3.5" />
                  <span>Resume</span>
                </Button>
              )}

              <Button
                variant="default"
                size="sm"
                className="h-8 px-2.5 text-xs gap-1"
                onClick={nextStep}
              >
                <span>{currentStepIndex === totalSteps - 1 ? "Finish" : "Next"}</span>
                <SkipForward className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
