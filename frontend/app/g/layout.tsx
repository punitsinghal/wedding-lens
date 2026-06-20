export default function GuestLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="antialiased bg-gray-50 text-gray-900 min-h-screen">
      {children}
    </div>
  );
}
