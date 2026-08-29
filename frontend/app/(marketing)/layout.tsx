import { BureauChrome } from "@/components/marketing/BureauChrome";
import { BureauFooter } from "@/components/marketing/BureauFooter";

/**
 * The public shell: fixed chrome, the page, an inverted footer.
 *
 * No theme toggle. Every other surface in the product offers one, and this one
 * does not: the landing page is a printed object with a decided ground, and a
 * reader who inverts it gets a different composition rather than the same one at
 * night. The footer already does the inversion, deliberately and once.
 */
export default function MarketingLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="ground-light bg-paper text-ink">
      <BureauChrome />
      <main>{children}</main>
      <BureauFooter />
    </div>
  );
}
