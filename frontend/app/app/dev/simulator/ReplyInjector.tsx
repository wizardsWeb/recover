"use client";

import { MessageSquarePlus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import {
  getFixtureStatus,
  getSimulatorStatus,
  injectReply,
  type InFlightCase,
  type ReplyChannel,
  type ReplyExample,
} from "@/lib/api/simulator";
import { Panel, useSimulatorRefresh } from "./SimulatorPanels";

const CHANNELS: ReplyChannel[] = ["whatsapp", "sms", "email"];

/** How long each example sits in the placeholder before the next one. */
const PLACEHOLDER_ROTATION_MS = 5000;

function caseLabel(item: InFlightCase): string {
  const shortId = item.id.slice(0, 8);
  const who = item.customerName ?? "unknown customer";
  return `Case ${shortId} · ${who} · ${item.playbook} · ${item.status}`;
}

export function ReplyInjector() {
  const { token, refresh } = useSimulatorRefresh();
  const [cases, setCases] = useState<InFlightCase[]>([]);
  const [examples, setExamples] = useState<ReplyExample[]>([]);
  const [caseId, setCaseId] = useState("");
  const [channel, setChannel] = useState<ReplyChannel>("whatsapp");
  const [text, setText] = useState("");
  const [exampleIndex, setExampleIndex] = useState(0);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function read() {
      try {
        const [status, fixtures] = await Promise.all([getSimulatorStatus(), getFixtureStatus()]);
        if (cancelled) return;
        setCases(status.inFlightCases);
        setExamples(fixtures.replyExamples);
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof ApiError ? error.message : "Could not load open cases");
        }
      }
    }

    void read();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Derived rather than stored, so a reset (which empties the list) and a fresh
  // firing (which prepends to it) both land on a valid selection without an
  // effect racing the render that shows the stale one.
  const activeCaseId = cases.some((item) => item.id === caseId) ? caseId : (cases[0]?.id ?? "");

  useEffect(() => {
    if (examples.length === 0) return;
    const timer = window.setInterval(
      () => setExampleIndex((index) => (index + 1) % examples.length),
      PLACEHOLDER_ROTATION_MS,
    );
    return () => window.clearInterval(timer);
  }, [examples.length]);

  const example = examples[exampleIndex];

  async function onInject() {
    if (!activeCaseId || !text.trim()) return;
    setSending(true);
    try {
      const result = await injectReply({ caseId: activeCaseId, channel, rawText: text.trim() });
      toast.success(result.message);
      setText("");
      refresh();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not inject reply");
    } finally {
      setSending(false);
    }
  }

  return (
    <Panel
      title="Reply injector"
      description="Send a customer reply into an open case, as if it arrived on WhatsApp"
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
          <NativeSelect
            className="w-full"
            value={activeCaseId}
            onChange={(event) => setCaseId(event.target.value)}
            aria-label="Case"
            disabled={cases.length === 0}
          >
            {cases.length === 0 ? (
              <NativeSelectOption value="">No open cases — fire a scenario first</NativeSelectOption>
            ) : (
              cases.map((item) => (
                <NativeSelectOption key={item.id} value={item.id}>
                  {caseLabel(item)}
                </NativeSelectOption>
              ))
            )}
          </NativeSelect>

          <NativeSelect
            className="w-full"
            value={channel}
            onChange={(event) => setChannel(event.target.value as ReplyChannel)}
            aria-label="Channel"
          >
            {CHANNELS.map((item) => (
              <NativeSelectOption key={item} value={item}>
                {item}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>

        <div>
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={example ? `e.g. ${example.text}` : "Type the customer's reply…"}
            rows={3}
            aria-label="Reply text"
          />
          <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => example && setText(example.text)}
              disabled={!example}
              className="text-xs font-medium text-brand underline-offset-4 hover:underline disabled:opacity-50"
            >
              Insert example →
            </button>
            {example && (
              <p className="text-xs text-ink-faint">
                expects <span className="font-mono">{example.expectedIntent}</span> ·{" "}
                {example.language}
              </p>
            )}
          </div>
        </div>

        <Button onClick={onInject} disabled={sending || !activeCaseId || !text.trim()}>
          {sending ? (
            <Spinner />
          ) : (
            <MessageSquarePlus className="size-4" strokeWidth={1.75} aria-hidden />
          )}
          Inject reply
        </Button>
      </div>
    </Panel>
  );
}
