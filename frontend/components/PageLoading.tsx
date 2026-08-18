// fullScreen: true for standalone pages, false when nested under a layout
// that already renders its own chrome (e.g. the event nav row) above this.
export default function PageLoading({ fullScreen = true }: { fullScreen?: boolean }) {
  return (
    <div className={`flex items-center justify-center ${fullScreen ? 'min-h-screen' : 'py-16'}`}>
      {/* eslint-disable-next-line @next/next/no-img-element -- animated gif, next/image won't animate it */}
      <img src="/loading.gif" alt="Loading" className="w-48 sm:w-56" />
    </div>
  );
}
