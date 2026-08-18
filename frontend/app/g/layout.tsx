export default function GuestLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="antialiased bg-bg text-ink min-h-screen">
      {children}
    </div>
  );
}
