export default function HomePage() {
  return (
    <>
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl items-center px-4 py-4">
          <span className="text-lg font-semibold tracking-tight">Cornerpin</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Subdivision lots, on the map
        </h1>
        <p className="mt-3 max-w-prose text-muted">
          Browse lots by status and price, see where they are, and look through photos and
          documents.
        </p>
      </main>
    </>
  );
}
