/**
 * Public environment values, read once and validated at module load.
 *
 * Next.js inlines `process.env.NEXT_PUBLIC_*` at build time, so these must be
 * referenced by their full literal name — destructuring `process.env` would
 * leave them undefined in the browser bundle.
 */

function required(value: string | undefined, name: string): string {
  if (!value) {
    throw new Error(
      `Missing ${name}. Copy .env.example to .env.local and fill in your Supabase credentials.`,
    );
  }
  return value;
}

export const env = {
  supabaseUrl: required(process.env.NEXT_PUBLIC_SUPABASE_URL, "NEXT_PUBLIC_SUPABASE_URL"),
  supabaseAnonKey: required(
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  ),
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  environment: process.env.NEXT_PUBLIC_ENVIRONMENT ?? "local",
} as const;

/** True in local development, where the Simulator and dev hints are shown. */
export const isLocal = env.environment === "local";
