import { getApps, getApp, initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  type Auth,
  type UserCredential,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || "AIzaSyCyQDJI7-3uZJsS69B1SEoJLIuajmWQC5A",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || "jkr-calling-d62f9.firebaseapp.com",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || "jkr-calling-d62f9",
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || "jkr-calling-d62f9.firebasestorage.app",
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || "841762891977",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || "1:841762891977:web:4adff5e56af164ec238518",
};

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function isFirebaseConfigured(): boolean {
  return Boolean(
    firebaseConfig.apiKey &&
      firebaseConfig.projectId &&
      firebaseConfig.authDomain
  );
}

export function getFirebaseAuth(): Auth | null {
  if (typeof window === "undefined") return null;

  try {
    if (!app) {
      const activeApps = getApps();
      app = activeApps.length > 0 ? getApp() : initializeApp(firebaseConfig);
    }
    if (!auth && app) {
      auth = getAuth(app);
    }
    return auth;
  } catch (err) {
    console.error("[FIREBASE INIT ERROR]", err);
    return null;
  }
}

function createGoogleProvider(): GoogleAuthProvider {
  const provider = new GoogleAuthProvider();
  // Ensure the real Google account chooser always appears
  provider.setCustomParameters({ prompt: "select_account" });
  return provider;
}

export async function signInWithGoogle(): Promise<{ idToken: string; email: string | null }> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    throw new Error(
      "Firebase Auth is not initialized. Please ensure environment variables are configured."
    );
  }

  const provider = createGoogleProvider();

  try {
    const result: UserCredential = await signInWithPopup(authInstance, provider);
    const idToken = await result.user.getIdToken();
    return {
      idToken,
      email: result.user.email,
    };
  } catch (error: any) {
    // If popup was blocked, we propagate the error code so the caller can trigger redirect or fallback
    if (error?.code === "auth/popup-blocked") {
      console.warn("[FIREBASE] Popup blocked by browser, fallback to redirect available");
    }
    throw error;
  }
}

export async function signInWithGoogleRedirect(): Promise<void> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    throw new Error("Firebase Auth is not initialized.");
  }

  const provider = createGoogleProvider();
  await signInWithRedirect(authInstance, provider);
}

export async function checkRedirectResult(): Promise<{ idToken: string; email: string | null } | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) return null;

  try {
    const result = await getRedirectResult(authInstance);
    if (!result) return null;
    const idToken = await result.user.getIdToken();
    return {
      idToken,
      email: result.user.email,
    };
  } catch (error) {
    console.error("[FIREBASE REDIRECT ERROR]", error);
    throw error;
  }
}
