/* Always serve the newest version of the game.
   GitHub Pages lets browsers reuse files for 10 minutes, so after an update players could get
   old and new files mixed. This worker asks the server for the game's own code on every load
   ("no-cache" = revalidate: usually a tiny 304 reply, a full download only when the file
   changed). Big versioned files (vendor/, models, videos, audio) keep normal caching. */
const FRESH = /\.(?:html|js|mjs|css|json|zip|webmanifest)$/;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.includes("/vendor/") || url.pathname.includes("/api/")) return;
  const page = req.mode === "navigate";
  if (!page && !FRESH.test(url.pathname)) return;
  const fresh = page ? fetch(req.url, { cache: "no-cache", credentials: "same-origin" }) : fetch(new Request(req, { cache: "no-cache" }));
  event.respondWith(fresh.catch(() => fetch(req)));
});
