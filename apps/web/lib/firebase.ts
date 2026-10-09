import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  type Auth,
  type UserCredential,
} from "firebase/auth";

const FIREBASE_DEFAULT_CONFIG = {
  apiKey: "AIzaSyALaBBV9G2t2dfLDRwz1xzJOUKwQkBsrB0",
  authDomain: "jkr-calling.firebaseapp.com",
  projectId: "jkr-calling",
  storageBucket: "jkr-calling.firebasestorage.app",
  messagingSenderId: "174011280990",
  appId: "1:174011280990:web:f8796d58288f3bd5b14ecf",
};

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || FIREBASE_DEFAULT_CONFIG.apiKey,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || FIREBASE_DEFAULT_CONFIG.authDomain,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || FIREBASE_DEFAULT_CONFIG.projectId,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || FIREBASE_DEFAULT_CONFIG.storageBucket,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || FIREBASE_DEFAULT_CONFIG.messagingSenderId,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || FIREBASE_DEFAULT_CONFIG.appId,
};

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });

export function isFirebaseConfigured(): boolean {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);
}

export function getFirebaseAuth(): Auth | null {
  if (typeof window === "undefined") return null;
  if (!isFirebaseConfigured()) return null;

  if (!app) {
    const existingApps = getApps();
    app = existingApps.length > 0 && existingApps[0] ? existingApps[0] : initializeApp(firebaseConfig);
  }
  if (!auth && app) {
    auth = getAuth(app);
  }
  return auth;
}

export async function signInWithGoogle(): Promise<{ idToken: string; email: string | null }> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    throw new Error(
      "Firebase configuration is missing. Please set NEXT_PUBLIC_FIREBASE_API_KEY and NEXT_PUBLIC_FIREBASE_PROJECT_ID."
    );
  }

  try {
    // Attempt popup flow first
    const result: UserCredential = await signInWithPopup(authInstance, googleProvider);
    const idToken = await result.user.getIdToken();
    return {
      idToken,
      email: result.user.email,
    };
  } catch (error: any) {
    // If popup was blocked or mobile webview environment, offer/fallback redirect
    if (
      error?.code === "auth/popup-blocked" ||
      error?.code === "auth/operation-not-supported-in-this-environment"
    ) {
      await signInWithRedirect(authInstance, googleProvider);
      // Window will redirect to Google
      return new Promise(() => {}); // never resolves because page redirects
    }
    throw error;
  }
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
    console.error("Error processing Google redirect result:", error);
    throw error;
  }
}
