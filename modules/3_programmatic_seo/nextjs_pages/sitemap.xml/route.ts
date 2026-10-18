/**
 * route.ts — Dynamic sitemap.xml via Next.js Route Handler
 * Place at: app/sitemap.xml/route.ts
 * Returns streaming XML sitemap for all movie/tv pages.
 */

import { NextResponse } from "next/server";

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://web-umber-six-e1un7z6257.vercel.app";
const TMDB_KEY = process.env.TMDB_API_KEY ?? "";

function toSlug(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .trim();
}

async function fetchPageSlugs(): Promise<{ slug: string; type: "movie" | "tv"; updated: string }[]> {
  const endpoints: Array<{ path: string; type: "movie" | "tv" }> = [
    { path: "movie/popular",        type: "movie" },
    { path: "movie/top_rated",      type: "movie" },
    { path: "trending/movie/week",  type: "movie" },
    { path: "tv/popular",           type: "tv"    },
    { path: "tv/top_rated",         type: "tv"    },
    { path: "trending/tv/week",     type: "tv"    },
  ];

  const results: { slug: string; type: "movie" | "tv"; updated: string }[] = [];
  const seen = new Set<string>();

  for (const ep of endpoints) {
    for (let page = 1; page <= 10; page++) {
      try {
        const res  = await fetch(
          `https://api.themoviedb.org/3/${ep.path}?api_key=${TMDB_KEY}&language=en-US&page=${page}`,
          { next: { revalidate: 86400 } }
        );
        const data = await res.json();
        for (const item of data.results ?? []) {
          const title = item.title ?? item.name ?? "";
          const slug  = toSlug(title);
          if (slug && !seen.has(slug)) {
            seen.add(slug);
            results.push({
              slug,
              type:    ep.type,
              updated: item.release_date ?? item.first_air_date ?? new Date().toISOString().slice(0, 10),
            });
          }
        }
      } catch {
        // continue on error
      }
    }
  }

  return results;
}

function buildSitemap(
  items: { slug: string; type: string; updated: string }[],
  today: string
): string {
  const staticPages = [
    { loc: BASE_URL,                  lastmod: today, changefreq: "daily",   priority: "1.0" },
    { loc: `${BASE_URL}/trending`,    lastmod: today, changefreq: "daily",   priority: "0.9" },
    { loc: `${BASE_URL}/genres`,      lastmod: today, changefreq: "weekly",  priority: "0.8" },
    { loc: `${BASE_URL}/top-rated`,   lastmod: today, changefreq: "weekly",  priority: "0.8" },
    { loc: `${BASE_URL}/new-releases`,lastmod: today, changefreq: "daily",   priority: "0.9" },
  ];

  const dynamicUrls = items.map((item) => ({
    loc:        `${BASE_URL}/movie/${item.slug}`,
    lastmod:    item.updated || today,
    changefreq: "weekly",
    priority:   "0.8",
  }));

  const allUrls = [...staticPages, ...dynamicUrls];

  const urlElements = allUrls
    .map(
      (u) => `  <url>
    <loc>${u.loc}</loc>
    <lastmod>${u.lastmod}</lastmod>
    <changefreq>${u.changefreq}</changefreq>
    <priority>${u.priority}</priority>
  </url>`
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
${urlElements}
</urlset>`;
}

export async function GET(): Promise<NextResponse> {
  const today = new Date().toISOString().slice(0, 10);
  const items = await fetchPageSlugs();
  const xml   = buildSitemap(items, today);

  return new NextResponse(xml, {
    status: 200,
    headers: {
      "Content-Type":  "application/xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=3600",
    },
  });
}
