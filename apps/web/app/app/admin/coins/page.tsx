import { adminCoinsApi } from "@jkr/sdk";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";
import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminCoinsReview } from "@/components/admin-coins-review";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AdminCoinsPage() {
  const { me, cookieHeader } = await getActiveWorkspaceContext();

  if (!me?.user) {
    notFound();
  }

  // Strict Super Admin Access Control using existing is_platform_super_admin flag
  if (!me.user.is_platform_super_admin) {
    return (
      <div className="p-8 max-w-xl mx-auto mt-12">
        <Card className="border-rose-500/40 bg-surface shadow-xl">
          <CardHeader>
            <div className="flex items-center gap-3 text-rose-400">
              <ShieldAlert className="h-6 w-6" />
              <CardTitle className="text-lg">Super-Admin Access Required</CardTitle>
            </div>
            <CardDescription>
              This section is strictly reserved for the platform owner to verify UPI payment proofs and manage coin distribution.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-xs text-muted-foreground">
            <p>
              Your account (<strong className="text-foreground">{me.user.email}</strong>) does not have the platform super-admin role enabled.
            </p>
            <Link
              href="/app/billing"
              className="inline-block rounded-lg bg-primary px-4 py-2 font-bold text-black hover:bg-primary/90 transition-all text-xs"
            >
              Return to Coin Wallet
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  const requests = await adminCoinsApi.listTopupRequests(undefined, { cookieHeader });

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto">
      <AdminCoinsReview initialRequests={requests} />
    </div>
  );
}
