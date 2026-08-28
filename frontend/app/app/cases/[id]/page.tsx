import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CaseStatusBadge } from "@/components/domain/CaseStatusBadge";
import { CaseTimeline } from "@/components/domain/CaseTimeline";
import { PlaybookBadge } from "@/components/domain/PlaybookBadge";
import { UpliftBucketBadge } from "@/components/domain/UpliftBucketBadge";
import { PageHeader } from "@/components/shell/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CaseDetail } from "@/lib/api/cases";
import { getCase } from "@/lib/api/cases.server";
import { formatINR, formatRelativeTime } from "@/lib/utils/format";
import { CaseActions } from "./CaseActions";

export const metadata: Metadata = { title: "Case" };

export default async function CaseDetailPage({ params }: PageProps<"/app/cases/[id]">) {
  const { id } = await params;

  let caseDetail: CaseDetail;
  try {
    caseDetail = await getCase(id);
  } catch {
    notFound();
  }

  const customer = caseDetail.customers;
  const isOptedOut = Boolean(customer?.consent?.opted_out_at);

  return (
    <>
      <PageHeader
        title={`Case ${caseDetail.id.slice(0, 8).toUpperCase()}`}
        subtitle={`Opened ${formatRelativeTime(caseDetail.opened_at)}`}
        actions={
          <div className="flex items-center gap-2">
            <CaseStatusBadge status={caseDetail.status} />
            <UpliftBucketBadge bucket={caseDetail.uplift_bucket} />
            <PlaybookBadge playbook={caseDetail.playbook} />
            <span className="font-mono text-sm text-ink-muted">
              {formatINR(caseDetail.amount_at_risk_cents)} at risk
            </span>
            {caseDetail.amount_recovered_cents > 0 ? (
              <span className="font-mono text-sm text-success">
                → {formatINR(caseDetail.amount_recovered_cents)} recovered
              </span>
            ) : null}
          </div>
        }
      />

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <h2 className="mb-4 text-sm font-semibold tracking-wider text-ink-muted uppercase">
            Agent Steps
          </h2>
          <CaseTimeline caseDetail={caseDetail} />
        </div>

        <div className="space-y-4">
          <Card className="border-hairline">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">Customer</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {customer ? (
                <>
                  <div>
                    <div className="font-medium text-ink">{customer.name ?? "Unknown"}</div>
                    <div className="text-xs text-ink-faint">{customer.email ?? "—"}</div>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-ink-faint">LTV</span>
                      <span className="font-mono font-medium">{formatINR(customer.ltv_cents)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink-faint">Tenure</span>
                      <span className="font-mono">{customer.tenure_days} days</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink-faint">Opted out</span>
                      {/* Opted-out is red not because it is a failure but because
                          it is the hardest constraint on the page: nothing else
                          the agent might do matters once this says Yes. */}
                      <span className={isOptedOut ? "font-medium text-danger" : "text-success"}>
                        {isOptedOut ? "Yes" : "No"}
                      </span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-ink-faint">Customer data unavailable</p>
              )}
            </CardContent>
          </Card>

          {/* Rendered for every case, closed ones included. `CaseActions`
              disables itself once a case is terminal, so the panel does not
              vanish out from under a reader the moment the agent closes it.
              Dropped on print: a button is not an audit record. */}
          <Card className="border-hairline print:hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent>
              <CaseActions caseId={caseDetail.id} status={caseDetail.status} />
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
