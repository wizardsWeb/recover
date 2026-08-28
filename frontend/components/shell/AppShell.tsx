import type { ReactNode } from "react";

import { Header } from "@/components/shell/Header";
import { PageContainer } from "@/components/shell/PageContainer";
import { Sidebar } from "@/components/shell/Sidebar";

interface AppShellProps {
  children: ReactNode;
  email: string;
  businessName: string;
  showDevTools: boolean;
  defaultSidebarCollapsed: boolean;
}

/**
 * Sidebar plus a scrolling main column.
 *
 * `h-dvh` with `overflow-y-auto` on the main column rather than page scroll:
 * it keeps the sidebar and header fixed without taking them out of flow, so
 * the collapsed/expanded sidebar width is the only thing the layout has to
 * respond to.
 */
export function AppShell({
  children,
  email,
  businessName,
  showDevTools,
  defaultSidebarCollapsed,
}: AppShellProps) {
  return (
    <div className="flex h-dvh overflow-hidden bg-base print:block print:h-auto print:overflow-visible">
      <Sidebar
        showDevTools={showDevTools}
        defaultCollapsed={defaultSidebarCollapsed}
        businessName={businessName}
        email={email}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header email={email} businessName={businessName} />
        <main className="flex-1 overflow-y-auto print:overflow-visible">
          <PageContainer>{children}</PageContainer>
        </main>
      </div>
    </div>
  );
}
