import { z } from "zod";

export const CoinTierSchema = z.object({
  id: z.string(),
  price_inr: z.number().int().positive(),
  base_coins: z.number().int().positive(),
  bonus_coins: z.number().int().nonnegative(),
  total_coins: z.number().int().positive(),
  label: z.string().optional(),
  tag: z.string().optional(),
});

export type CoinTier = z.infer<typeof CoinTierSchema>;

export const COIN_TIERS: CoinTier[] = [
  { id: "tier_100", price_inr: 100, base_coins: 300, bonus_coins: 0, total_coins: 300, label: "Starter" },
  { id: "tier_250", price_inr: 250, base_coins: 800, bonus_coins: 50, total_coins: 850, label: "Most Popular", tag: "+50 Bonus" },
  { id: "tier_400", price_inr: 400, base_coins: 1350, bonus_coins: 0, total_coins: 1350, label: "Pro Value" },
];

export const CoinWalletOutSchema = z.object({
  workspace_id: z.string().uuid(),
  balance_coins: z.number().int(),
  total_recharged_coins: z.number().int(),
  total_spent_coins: z.number().int(),
});

export type CoinWalletOut = z.infer<typeof CoinWalletOutSchema>;

export const CoinTopupRequestCreateSchema = z.object({
  tier_id: z.string(),
  screenshot_base64: z.string().min(1, "Screenshot proof is required"),
  screenshot_filename: z.string().optional(),
});

export type CoinTopupRequestCreate = z.infer<typeof CoinTopupRequestCreateSchema>;

export const CoinTopupRequestOutSchema = z.object({
  id: z.string().uuid(),
  workspace_id: z.string().uuid(),
  workspace_name: z.string().optional(),
  user_id: z.string().uuid(),
  user_email: z.string().optional(),
  tier_id: z.string(),
  price_inr: z.number().int(),
  base_coins: z.number().int(),
  bonus_coins: z.number().int(),
  total_coins: z.number().int(),
  screenshot_url: z.string(),
  status: z.enum(["pending", "approved", "rejected"]),
  admin_notes: z.string().nullable().optional(),
  reviewed_by: z.string().uuid().nullable().optional(),
  reviewed_at: z.string().datetime({ offset: true }).nullable().optional(),
  created_at: z.string().datetime({ offset: true }),
});

export type CoinTopupRequestOut = z.infer<typeof CoinTopupRequestOutSchema>;

export const CoinTransactionOutSchema = z.object({
  id: z.string().uuid(),
  workspace_id: z.string().uuid(),
  user_id: z.string().uuid().nullable().optional(),
  amount_coins: z.number().int(),
  transaction_type: z.string(),
  reference_id: z.string().nullable().optional(),
  description: z.string(),
  balance_after: z.number().int(),
  created_at: z.string().datetime({ offset: true }),
});

export type CoinTransactionOut = z.infer<typeof CoinTransactionOutSchema>;

export const AdminApproveRejectSchema = z.object({
  notes: z.string().optional(),
});

export type AdminApproveReject = z.infer<typeof AdminApproveRejectSchema>;
