import { adminCoinsApi } from "@jkr/sdk";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AdminDashboard } from "@/components/admin-dashboard";
import { getServerSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const REQUIRED_ADMIN_EMAIL = "jkrcalling4@gmail.com";

export default async function AdminPage() {
  const me = await getServerSession();

  if (!me) {
    redirect("/admin/login");
  }

  // Strict email gate: reject any email other than jkrcalling4@gmail.com
  if (me.user.email.trim().toLowerCase() !== REQUIRED_ADMIN_EMAIL) {
    redirect("/admin/login?error=forbidden");
  }

  const cookieHeader = cookies().toString();

  const [overview, requests] = await Promise.all([
    adminCoinsApi.getOverview({ cookieHeader }).catch((err) => {
      console.error("[ADMIN OVERVIEW FETCH ERROR]", err);
      return null;
    }),
    adminCoinsApi.listTopupRequests(undefined, { cookieHeader }).catch((err) => {
      console.error("[ADMIN REQUESTS FETCH ERROR]", err);
      return [];
    }),
  ]);

  return (
    <AdminDashboard
      currentUser={me.user}
      initialOverview={overview}
      initialRequests={requests}
    />
  );
}
