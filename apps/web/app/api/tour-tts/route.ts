import { NextResponse } from "next/server";

const SARVAM_TTS_API_KEY =
  process.env.SARVAM_TTS_API_KEY ||
  process.env.SARVAM_API_KEY ||
  "sk_6j3tpcb6_XPvivuSgqREvn86HOoEFFtHt";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { text, language_code = "en-IN", speaker = "priya" } = body;

    if (!text || typeof text !== "string") {
      return NextResponse.json({ error: "Missing text parameter" }, { status: 400 });
    }

    // Call Sarvam AI TTS API (Bulbul v3)
    const response = await fetch("https://api.sarvam.ai/text-to-speech", {
      method: "POST",
      headers: {
        "api-subscription-key": SARVAM_TTS_API_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        language_code,
        speaker,
        model: "bulbul:v3",
        pace: 1.05,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.warn("Sarvam TTS API failed with status:", response.status, errorText);
      return NextResponse.json(
        {
          error: `Sarvam API error: ${response.status}`,
          details: errorText,
          fallback: "browser",
        },
        { status: 200 } // Return 200 with fallback signal so frontend smoothly handles browser speech
      );
    }

    const data = await response.json();
    const audioBase64 = data.audios && data.audios[0] ? data.audios[0] : null;

    if (!audioBase64) {
      return NextResponse.json(
        { error: "No audio returned from Sarvam", fallback: "browser" },
        { status: 200 }
      );
    }

    return NextResponse.json({
      audioBase64,
      provider: "sarvam",
      speaker,
      language_code,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Internal error";
    console.error("Error in /api/tour-tts:", error);
    return NextResponse.json(
      { error: message, fallback: "browser" },
      { status: 200 }
    );
  }
}
