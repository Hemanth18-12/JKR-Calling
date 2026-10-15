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

const FIREBASE_API_KEY =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_FIREBASE_API_KEY) ||
  "AIzaSyALaBBV9G2t2dfLDRwz1xzJOUKwQkBsrB0";

const FIREBASE_PROJECT_ID =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID) || "jkr-calling";

const FIREBASE_AUTH_DOMAIN =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN) ||
  "jkr-calling.firebaseapp.com";

const firebaseConfig = {
  apiKey: FIREBASE_API_KEY,
  authDomain: FIREBASE_AUTH_DOMAIN,
  projectId: FIREBASE_PROJECT_ID,
  storageBucket:
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET) ||
    "jkr-calling.firebasestorage.app",
  messagingSenderId:
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID) ||
    "174011280990",
  appId:
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_FIREBASE_APP_ID) ||
    "1:174011280990:web:f8796d58288f3bd5b14ecf",
};

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function isFirebaseConfigured(): boolean {
  return true;
}

export function getFirebaseAuth(): Auth | null {
  if (typeof window === "undefined") return null;
  if (!isFirebaseConfigured()) return null;

  try {
    if (!app) {
      const existingApps = getApps();
      app = existingApps.length > 0 && existingApps[0] ? existingApps[0] : initializeApp(firebaseConfig);
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

export async function signInWithGoogle(): Promise<{ idToken: string; email: string | null }> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    throw new Error(
      "Firebase configuration is missing or could not be initialized. Please check your network or environment variables."
    );
  }

  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });

  try {
    const result: UserCredential = await signInWithPopup(authInstance, provider);
    const idToken = await result.user.getIdToken();
    return {
      idToken,
      email: result.user.email,
    };
  } catch (error: any) {
    console.error("[FIREBASE POPUP ERROR]", error?.code, error?.message);
    throw error;
  }
}

export async function signInWithGoogleRedirect(): Promise<void> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    throw new Error("Firebase configuration is missing.");
  }

  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
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
    console.error("[FIREBASE REDIRECT RESULT ERROR]", error);
    throw error;
  }
}
