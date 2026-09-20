/** Keep Jinja chrome hidden when a classic page is framed inside the React shell. */
export function withEmbedParam(href: string): string {
  const u = new URL(href, "http://local.invalid");
  u.searchParams.set("embed", "1");
  return `${u.pathname}${u.search}${u.hash}`;
}

export function ClassicFrame({ title, src }: { title: string; src: string }) {
  return (
    <iframe
      title={title}
      src={withEmbedParam(src)}
      className="block h-[calc(100vh-3.5rem)] w-full border-0 bg-white"
    />
  );
}

export function classicFramePage(opts: { title: string; src: string }) {
  function Page() {
    return <ClassicFrame title={opts.title} src={opts.src} />;
  }
  Page.displayName = `${opts.title}Page`;
  return Page;
}
