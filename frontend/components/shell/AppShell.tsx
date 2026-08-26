import type { ReactNode } from "react";

import { Header } from "@/components/shell/Header";
import { PageContainer } from "@/components/shell/PageContainer";
import { Sidebar } from "@/components/shell/Sidebar";

interface AppShellProps {
  children: ReactNode;
  email: string;
  businessName: string;
  showDevTools: boolean;
}

/**
 * Sidebar plus a scrolling main column.
 *
 * `h-dvh` with `overflow-y-auto` on the main column rather than page scroll:
 * it keeps the sidebar and header fixed without taking them out of flow, so
 * the collapsed/expanded sidebar width is the only thing the layout has to
 * respond to.
 */
export function AppShell({ children, email, businessName, showDevTools }: AppShellProps) {
  return (
    <div className="flex h-dvh overflow-hidden bg-base">
      <Sidebar showDevTools={showDevTools} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header email={email} businessName={businessName} />
        <main className="flex-1 overflow-y-auto">
          <PageContainer>{children}</PageContainer>
        </main>
      </div>
    </div>
  );
}
