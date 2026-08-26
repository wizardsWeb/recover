/**
 * Hand-written row types for the tables Phase 1 touches.
 *
 * Phase 2 replaces this file with the full generated schema:
 *   supabase gen types typescript --project-id <ref> > lib/supabase/types.ts
 *
 * Only `merchants` is modelled here because it is the only table the frontend
 * reads directly; everything else arrives through the FastAPI backend.
 */

import type { SetAllCookies } from "@supabase/ssr";

/**
 * The array `setAll` is handed by @supabase/ssr.
 *
 * Declared explicitly because the `cookies` option is typed as a union of the
 * current and deprecated method shapes, and TypeScript will not contextually
 * type a callback parameter through a union — without this the parameter is an
 * implicit `any` and `strict` rejects it.
 */
export type CookiesToSet = Parameters<SetAllCookies>[0];

export type Vertical = "d2c_beauty" | "edtech_subscription" | "b2b_distribution" | "other";

/**
 * Declared as a `type`, not an `interface`, on purpose.
 *
 * postgrest-js constrains every table's `Row` to `Record<string, unknown>`.
 * A type alias gets an implicit index signature and satisfies that; an
 * interface does not, because declaration merging means TypeScript cannot
 * prove the key set is closed. Get this wrong and the schema silently
 * resolves to `never`, so every `.select()` returns `null`.
 */
export type MerchantRow = {
  id: string;
  name: string;
  vertical: Vertical | null;
  onboarded: boolean;
  playbook_config: Record<string, unknown>;
  timezone: string;
  created_at: string;
  updated_at: string;
};

export type Database = {
  public: {
    Tables: {
      merchants: {
        Row: MerchantRow;
        Insert: Partial<MerchantRow> & Pick<MerchantRow, "id" | "name">;
        Update: Partial<MerchantRow>;
        Relationships: [];
      };
    };
    Views: Record<never, never>;
    Functions: Record<never, never>;
    Enums: Record<never, never>;
    CompositeTypes: Record<never, never>;
  };
};
