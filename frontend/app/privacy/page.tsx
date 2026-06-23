// Static privacy notice — no backend call, unauthenticated (NFR-5, REQ-7)
import Link from 'next/link';

export const metadata = {
  title: 'Privacy Notice — WeddingLens',
  description:
    'How WeddingLens collects, uses, and retains biometric face data under the Digital Personal Data Protection Act, 2023.',
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-gray-200 px-4 py-4">
        <div className="max-w-2xl mx-auto flex items-center gap-3">
          <Link
            href="/"
            className="text-sm text-gray-500 hover:text-gray-800 transition-colors"
          >
            &larr; Back
          </Link>
          <span className="text-gray-300">/</span>
          <span className="text-sm font-medium text-gray-700">Privacy Notice</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-10 space-y-8 text-gray-700">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 mb-1">
            Biometric Data Privacy Notice
          </h1>
          <p className="text-sm text-gray-500">
            Effective date: June 2026. English only for MVP.
          </p>
        </div>

        {/* Data Fiduciary */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">1. Who we are (Data Fiduciary)</h2>
          <p className="text-sm leading-relaxed">
            WeddingLens is the Data Fiduciary responsible for the personal data described in this
            notice. Event owners (photographers) use the platform to host photo galleries; they
            inform their guests about face recognition before publishing an event. The platform
            remains the Data Fiduciary for the biometric data processed — responsibility does not
            transfer to the event owner.
          </p>
        </section>

        {/* Data collected */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">2. What data we collect</h2>
          <p className="text-sm leading-relaxed">
            When you use the &ldquo;Find my photos&rdquo; feature, you upload a selfie. We derive a
            face embedding — a mathematical numerical representation of facial geometry — from that
            selfie. This embedding is the biometric data we process. Your actual selfie image is{' '}
            <strong>never stored</strong>; it is deleted from memory immediately after the embedding
            is computed and the search is complete.
          </p>
        </section>

        {/* Purpose */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">3. Why we collect it (Purpose)</h2>
          <p className="text-sm leading-relaxed">
            The sole purpose of collecting the face embedding is to search this event&apos;s photo
            index and identify which photos you appear in, so that you can find and download them.
            The embedding is not used for any other purpose, not shared with third parties, and not
            used to identify you outside of this event.
          </p>
        </section>

        {/* Legal basis */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">
            4. Legal basis (DPDP Act, 2023 &sect;6 — Consent)
          </h2>
          <p className="text-sm leading-relaxed">
            Processing is based on your explicit consent under Section 6 of India&apos;s Digital
            Personal Data Protection Act, 2023 (DPDP Act). Your consent is captured when you tap
            &ldquo;I understand, continue&rdquo; on the selfie upload screen. You may withdraw your
            consent at any time — see Section 6 below for instructions.
          </p>
          <p className="text-sm leading-relaxed">
            For guests under 18, a parent or guardian provides consent on their behalf. The
            affirmation at the upload step serves as the consent record for MVP.
          </p>
        </section>

        {/* Retention */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">5. How long we keep it (Retention)</h2>
          <ul className="text-sm leading-relaxed space-y-1 list-disc list-inside">
            <li>
              <strong>Your selfie:</strong> deleted immediately after the face search is complete.
              It is never written to disk.
            </li>
            <li>
              <strong>Your face embedding:</strong> stored in encrypted form and scoped to the
              specific event. It is automatically deleted — along with all other event data
              including photos — within 30 days of the event&apos;s end date.
            </li>
          </ul>
        </section>

        {/* Withdraw consent */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">6. How to withdraw consent</h2>
          <p className="text-sm leading-relaxed">
            You can withdraw consent for your face data at any time by submitting a face data
            removal request via the event gallery page (see the &ldquo;Remove my face data&rdquo;
            link in the gallery header). Once you submit the request, it will be processed within
            24 hours. Withdrawal does not affect the lawfulness of processing that occurred before
            withdrawal.
          </p>
        </section>

        {/* Removal request */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">
            7. How to submit a face data removal request
          </h2>
          <p className="text-sm leading-relaxed">
            Navigate to the gallery of the event you attended. In the header, tap
            &ldquo;Remove my face data&rdquo;. You will be asked for your name, email address, and
            a brief description of when you uploaded a selfie (to help us locate your data). After
            submission, you will receive an on-screen confirmation and the request will be
            processed within 24 hours.
          </p>
          <p className="text-sm leading-relaxed">
            The removal request form also serves as the contact path for any data-related grievance
            in this MVP phase.
          </p>
        </section>

        {/* Security */}
        <section className="space-y-2">
          <h2 className="text-base font-semibold text-gray-900">8. How we protect your data</h2>
          <p className="text-sm leading-relaxed">
            Face embeddings are encrypted at rest using AES-256-GCM. All data in transit is
            protected by TLS 1.2 or higher. Searches are strictly scoped per event — your
            embedding cannot be matched against any other event&apos;s photos.
          </p>
        </section>

        <hr className="border-gray-200" />

        <p className="text-xs text-gray-400">
          This notice covers the WeddingLens platform. For questions, use the removal request
          form in your event gallery.
        </p>
      </main>
    </div>
  );
}
