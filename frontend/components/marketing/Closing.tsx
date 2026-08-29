import Link from "next/link";

/**
 * The ask, as a sentence with a link in it.
 *
 * No button. A pill with a fill would be the only such object on the page and
 * would read as an advertisement dropped into an essay; an underlined link at
 * display size is louder in this context precisely because nothing else is
 * shouting. The underline is the affordance and the hover moves it.
 *
 * One destination. A second, quieter button beside it — "view on GitHub", the
 * usual pairing — would mean the page had not decided what it wanted, and the
 * repository link belongs in the footer with the other metadata.
 */
export function Closing() {
  return (
    <section id="start" className="bg-paper px-5 py-32 sm:px-7 sm:py-48">
      <p className="type-statement max-w-[24ch] text-ink">Start recovering.</p>

      {/* The link is its own block, not inline in the sentence above.
          At 0.92 leading an underline on a wrapping display-size link lands on
          top of the following line — the offset that clears the descenders of
          line one is already inside line two. Giving it a line of its own is the
          fix that keeps the link at display size; the alternative was demoting
          it to 13px, which would have made the one thing being asked for the
          quietest thing on the page. */}
      <p className="type-statement mt-2 text-ink">
        <Link
          href="/signup"
          className="link-rule decoration-ink-faint transition-colors duration-200 hover:decoration-ink"
        >
          Open an account
        </Link>
      </p>

      <p className="type-meta mt-8 max-w-[40ch]">
        Free, and on Razorpay test keys until you say otherwise. No card, no sales call.
      </p>
    </section>
  );
}
