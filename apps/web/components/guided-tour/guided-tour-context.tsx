"use client";

import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { PageTour, TOUR_SCRIPTS, TourLanguage, TourStep } from "@/lib/guided-tour-scripts";

interface GuidedTourContextType {
  isOpen: boolean;
  activePageId: string;
  currentStepIndex: number;
  isPlaying: boolean;
  language: TourLanguage;
  activeProvider: "sarvam" | "browser";
  isLoadingAudio: boolean;
  currentTour: PageTour | null;
  currentStep: TourStep | null;
  totalSteps: number;
  startTour: (pageId?: string) => void;
  stopTour: () => void;
  pauseTour: () => void;
  resumeTour: () => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (index: number) => void;
  setLanguage: (lang: TourLanguage) => void;
}

const GuidedTourContext = createContext<GuidedTourContextType | null>(null);

// Audio cache to prevent re-fetching the exact same audio multiple times
const audioCache = new Map<string, string>();

export function GuidedTourProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [activePageId, setActivePageId] = useState("dashboard");
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [language, setLanguage] = useState<TourLanguage>("en-IN");
  const [activeProvider, setActiveProvider] = useState<"sarvam" | "browser">("sarvam");
  const [isLoadingAudio, setIsLoadingAudio] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const currentTour = TOUR_SCRIPTS[activePageId] || null;
  const totalSteps = currentTour ? currentTour.steps.length : 0;
  const currentStep = currentTour && currentTour.steps[currentStepIndex] ? currentTour.steps[currentStepIndex] : null;

  // Clean up any ongoing audio or speech on unmount or close
  const stopAllAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
      audioRef.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  };

  // Play narration for the active step
  const playCurrentNarration = async (step: TourStep, lang: TourLanguage) => {
    stopAllAudio();
    const narrationText = step.narration[lang] || step.narration["en-IN"];
    const cacheKey = `${lang}:${narrationText}`;

    setIsLoadingAudio(true);
    setIsPlaying(true);

    // Try Sarvam TTS first
    try {
      let base64Audio = audioCache.get(cacheKey);

      if (!base64Audio) {
        abortControllerRef.current = new AbortController();
        const res = await fetch("/api/tour-tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: narrationText,
            language_code: lang,
            speaker: "priya",
          }),
          signal: abortControllerRef.current.signal,
        });

        if (res.ok) {
          const data = await res.json();
          const receivedAudio = data.audioBase64;
          if (typeof receivedAudio === "string" && receivedAudio.length > 0) {
            base64Audio = receivedAudio;
            audioCache.set(cacheKey, receivedAudio);
          }
        }
      }

      if (base64Audio) {
        setActiveProvider("sarvam");
        setIsLoadingAudio(false);

        const audio = new Audio(`data:audio/wav;base64,${base64Audio}`);
        audioRef.current = audio;

        audio.onended = () => {
          setIsPlaying(false);
          // Automatically advance to the next step after a short pause if not on the last step
          setTimeout(() => {
            setCurrentStepIndex((prev) => {
              if (currentTour && prev < currentTour.steps.length - 1) {
                return prev + 1;
              }
              return prev;
            });
          }, 800);
        };

        audio.onerror = (err) => {
          console.warn("Audio element error, falling back to speech synthesis:", err);
          fallbackToBrowserSpeech(narrationText, lang);
        };

        await audio.play();
        return;
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === "AbortError") {
        return;
      }
      console.warn("Sarvam TTS request failed, using browser speech fallback:", err);
    }

    // Fallback to browser Web Speech API
    fallbackToBrowserSpeech(narrationText, lang);
  };

  const fallbackToBrowserSpeech = (text: string, lang: TourLanguage) => {
    setIsLoadingAudio(false);
    setActiveProvider("browser");

    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = 1.0;

      utterance.onend = () => {
        setIsPlaying(false);
        setTimeout(() => {
          setCurrentStepIndex((prev) => {
            if (currentTour && prev < currentTour.steps.length - 1) {
              return prev + 1;
            }
            return prev;
          });
        }, 800);
      };

      utterance.onerror = () => {
        setIsPlaying(false);
      };

      window.speechSynthesis.speak(utterance);
      setIsPlaying(true);
    } else {
      setIsPlaying(false);
    }
  };

  // Whenever step or language changes while tour is open, play narration
  useEffect(() => {
    if (isOpen && currentStep) {
      playCurrentNarration(currentStep, language);
    }
  }, [currentStepIndex, isOpen, language]);

  // Scroll current element into view
  useEffect(() => {
    if (isOpen && currentStep) {
      const el = document.getElementById(currentStep.id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [currentStepIndex, isOpen]);

  const startTour = (pageId = "dashboard") => {
    setActivePageId(pageId);
    setCurrentStepIndex(0);
    setIsOpen(true);
  };

  const stopTour = () => {
    stopAllAudio();
    setIsOpen(false);
    setIsPlaying(false);
  };

  const pauseTour = () => {
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause();
    } else if (typeof window !== "undefined" && "speechSynthesis" in window && window.speechSynthesis.speaking) {
      window.speechSynthesis.pause();
    }
    setIsPlaying(false);
  };

  const resumeTour = () => {
    if (audioRef.current && audioRef.current.paused) {
      audioRef.current.play();
      setIsPlaying(true);
    } else if (typeof window !== "undefined" && "speechSynthesis" in window && window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      setIsPlaying(true);
    } else if (currentStep) {
      playCurrentNarration(currentStep, language);
    }
  };

  const nextStep = () => {
    if (currentTour && currentStepIndex < currentTour.steps.length - 1) {
      setCurrentStepIndex((prev) => prev + 1);
    } else {
      stopTour();
    }
  };

  const prevStep = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1);
    }
  };

  const goToStep = (index: number) => {
    if (currentTour && index >= 0 && index < currentTour.steps.length) {
      setCurrentStepIndex(index);
    }
  };

  return (
    <GuidedTourContext.Provider
      value={{
        isOpen,
        activePageId,
        currentStepIndex,
        isPlaying,
        language,
        activeProvider,
        isLoadingAudio,
        currentTour,
        currentStep,
        totalSteps,
        startTour,
        stopTour,
        pauseTour,
        resumeTour,
        nextStep,
        prevStep,
        goToStep,
        setLanguage,
      }}
    >
      {children}
    </GuidedTourContext.Provider>
  );
}

export function useGuidedTour() {
  const ctx = useContext(GuidedTourContext);
  if (!ctx) {
    throw new Error("useGuidedTour must be used within a GuidedTourProvider");
  }
  return ctx;
}
