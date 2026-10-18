import type { Metadata } from "next";
import { notFound } from "next/navigation";

const BASE_URL  = process.env.NEXT_PUBLIC_SITE_URL ?? "https://web-umber-six-e1un7z6257.vercel.app";
const TMDB_KEY  = process.env.TMDB_API_KEY ?? "";
const IMG_BASE  = "https://image.tmdb.org/t/p/original";
const IMG_W500  = "https://image.tmdb.org/t/p/w500";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Genre    { id: number; name: string }
interface CastMember { name: string; character: string; profile_path: string | null }

interface MovieData {
  id:             number;
  title:          string;
  slug:           string;
  overview:       string;
  release_date:   string;
  runtime:        number;
  vote_average:   number;
  vote_count:     number;
  popularity:     number;
  poster_path:    string | null;
  backdrop_path:  string | null;
  genres:         Genre[];
  cast:           CastMember[];
  tagline:        string;
  type:           "movie" | "tv";
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toSlug(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .trim();
}

async function fetchMovieBySlug(slug: string): Promise<MovieData | null> {
  // Search TMDb by title derived from slug
  const query = slug.replace(/-/g, " ");

  const searchRes = await fetch(
    `https://api.themoviedb.org/3/search/multi?api_key=${TMDB_KEY}&query=${encodeURIComponent(query)}&language=en-US`,
    { next: { revalidate: 86400 } }
  );

  if (!searchRes.ok) return null;
  const searchData = await searchRes.json();
  const results: any[] = searchData.results ?? [];

  const match = results.find(
    (r) =>
      (r.media_type === "movie" || r.media_type === "tv") &&
      toSlug(r.title ?? r.name ?? "") === slug
  ) ?? results[0];

  if (!match) return null;

  const type      = match.media_type === "tv" ? "tv" : "movie";
  const detailRes = await fetch(
    `https://api.themoviedb.org/3/${type}/${match.id}?api_key=${TMDB_KEY}&language=en-US&append_to_response=credits`,
    { next: { revalidate: 86400 } }
  );

  if (!detailRes.ok) return null;
  const detail = await detailRes.json();

  const cast: CastMember[] = (detail.credits?.cast ?? [])
    .slice(0, 12)
    .map((c: any) => ({ name: c.name, character: c.character, profile_path: c.profile_path }));

  return {
    id:            detail.id,
    title:         detail.title ?? detail.name ?? "",
    slug:          toSlug(detail.title ?? detail.name ?? ""),
    overview:      detail.overview ?? "",
    release_date:  detail.release_date ?? detail.first_air_date ?? "",
    runtime:       detail.runtime ?? detail.episode_run_time?.[0] ?? 0,
    vote_average:  detail.vote_average ?? 0,
    vote_count:    detail.vote_count ?? 0,
    popularity:    detail.popularity ?? 0,
    poster_path:   detail.poster_path,
    backdrop_path: detail.backdrop_path,
    genres:        detail.genres ?? [],
    cast,
    tagline:       detail.tagline ?? "",
    type,
  };
}

// ─── Static Params ────────────────────────────────────────────────────────────

export async function generateStaticParams() {
  const endpoints = [
    "movie/popular",
    "movie/top_rated",
    "trending/movie/week",
    "tv/popular",
    "tv/top_rated",
  ];

  const slugs: { slug: string }[] = [];
  const seen = new Set<string>();

  for (const endpoint of endpoints) {
    for (let page = 1; page <= 5; page++) {
      try {
        const res  = await fetch(
          `https://api.themoviedb.org/3/${endpoint}?api_key=${TMDB_KEY}&language=en-US&page=${page}`,
          { next: { revalidate: 86400 } }
        );
        const data = await res.json();
        for (const item of data.results ?? []) {
          const slug = toSlug(item.title ?? item.name ?? "");
          if (slug && !seen.has(slug)) {
            seen.add(slug);
            slugs.push({ slug });
          }
        }
      } catch {
        // skip failed pages
      }
    }
  }

  return slugs;
}

// ─── Metadata ─────────────────────────────────────────────────────────────────

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const movie = await fetchMovieBySlug(params.slug);
  if (!movie) return { title: "Not Found" };

  const year  = movie.release_date?.slice(0, 4) ?? "";
  const genre = movie.genres[0]?.name ?? "Movie";

  return {
    title:       `Watch ${movie.title} (${year}) Free in 4K | FilmFeed`,
    description: `Stream ${movie.title} online free in 4K HD. No sign-up required. ${movie.overview.slice(0, 140)}`,
    keywords:    [
      `watch ${movie.title} free`,
      `${movie.title} full movie`,
      `${movie.title} online`,
      `stream ${movie.title}`,
      `${movie.title} 4K`,
      `${movie.title} ${year}`,
      genre,
    ],
    openGraph: {
      title:       `${movie.title} — Watch Free in 4K`,
      description: movie.overview.slice(0, 200),
      images:      movie.poster_path ? [`${IMG_W500}${movie.poster_path}`] : [],
      type:        "video.movie",
      url:         `${BASE_URL}/movie/${movie.slug}`,
    },
    twitter: {
      card:        "summary_large_image",
      title:       `${movie.title} — Stream Free 4K`,
      description: movie.overview.slice(0, 200),
      images:      movie.poster_path ? [`${IMG_W500}${movie.poster_path}`] : [],
    },
    alternates: {
      canonical: `${BASE_URL}/movie/${movie.slug}`,
    },
  };
}

// ─── JSON-LD Structured Data ──────────────────────────────────────────────────

function JsonLD({ movie }: { movie: MovieData }) {
  const schema = {
    "@context":    "https://schema.org",
    "@type":       "Movie",
    name:          movie.title,
    description:   movie.overview,
    image:         movie.poster_path ? `${IMG_BASE}${movie.poster_path}` : undefined,
    datePublished: movie.release_date,
    genre:         movie.genres.map((g) => g.name),
    duration:      movie.runtime ? `PT${movie.runtime}M` : undefined,
    aggregateRating: movie.vote_count > 0 ? {
      "@type":       "AggregateRating",
      ratingValue:   movie.vote_average.toFixed(1),
      bestRating:    "10",
      worstRating:   "1",
      ratingCount:   movie.vote_count,
    } : undefined,
    actor: movie.cast.map((c) => ({ "@type": "Person", name: c.name })),
    url:   `${BASE_URL}/movie/${movie.slug}`,
    potentialAction: {
      "@type":  "WatchAction",
      target:   `${BASE_URL}/movie/${movie.slug}`,
    },
  };

  const videoSchema = {
    "@context":    "https://schema.org",
    "@type":       "VideoObject",
    name:          `${movie.title} — Full Movie Stream`,
    description:   movie.overview,
    thumbnailUrl:  movie.backdrop_path ? `${IMG_BASE}${movie.backdrop_path}` : undefined,
    uploadDate:    movie.release_date,
    embedUrl:      `${BASE_URL}/movie/${movie.slug}`,
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(videoSchema) }}
      />
    </>
  );
}

// ─── Page Component ───────────────────────────────────────────────────────────

export default async function MoviePage({ params }: { params: { slug: string } }) {
  const movie = await fetchMovieBySlug(params.slug);
  if (!movie) notFound();

  const year     = movie.release_date?.slice(0, 4) ?? "";
  const rating   = movie.vote_average.toFixed(1);
  const backdrop = movie.backdrop_path ? `${IMG_BASE}${movie.backdrop_path}` : null;
  const poster   = movie.poster_path   ? `${IMG_W500}${movie.poster_path}`   : null;

  return (
    <>
      <JsonLD movie={movie} />

      {/* Hero Section */}
      <section
        className="relative min-h-[70vh] flex items-end pb-12"
        style={{
          backgroundImage:    backdrop ? `url(${backdrop})` : "none",
          backgroundSize:     "cover",
          backgroundPosition: "center top",
        }}
      >
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/70 to-transparent" />

        <div className="relative z-10 container mx-auto px-4 flex flex-col md:flex-row gap-8 items-end">
          {/* Poster */}
          {poster && (
            <img
              src={poster}
              alt={`${movie.title} poster`}
              className="hidden md:block w-48 rounded-xl shadow-2xl border border-white/10 flex-shrink-0"
              loading="eager"
            />
          )}

          {/* Info */}
          <div className="flex-1">
            <div className="flex flex-wrap gap-2 mb-3">
              {movie.genres.map((g) => (
                <span
                  key={g.id}
                  className="px-3 py-1 text-xs font-semibold rounded-full bg-red-600/80 text-white uppercase tracking-wider"
                >
                  {g.name}
                </span>
              ))}
            </div>

            <h1 className="text-4xl md:text-6xl font-extrabold text-white leading-tight mb-2 drop-shadow-lg">
              {movie.title}
            </h1>

            {movie.tagline && (
              <p className="text-gray-300 italic text-lg mb-3">"{movie.tagline}"</p>
            )}

            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-300 mb-4">
              {year && <span className="font-medium">{year}</span>}
              {movie.runtime > 0 && (
                <span>{Math.floor(movie.runtime / 60)}h {movie.runtime % 60}m</span>
              )}
              <span className="flex items-center gap-1">
                <svg className="w-4 h-4 text-yellow-400 fill-yellow-400" viewBox="0 0 20 20">
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
                {rating} / 10
              </span>
              <span className="text-gray-500">({movie.vote_count.toLocaleString()} votes)</span>
            </div>

            <p className="text-gray-200 text-base leading-relaxed max-w-2xl mb-8 line-clamp-3">
              {movie.overview}
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-wrap gap-4">
              <a
                href={`${BASE_URL}/movie/${movie.slug}`}
                className="inline-flex items-center gap-2 px-8 py-4 bg-red-600 hover:bg-red-500 text-white font-bold text-lg rounded-xl shadow-lg shadow-red-900/50 transition-all duration-200 hover:scale-105"
              >
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
                Watch Free in 4K
              </a>
              <a
                href={`https://wa.me/?text=Request: ${encodeURIComponent(movie.title)} — ${BASE_URL}/movie/${movie.slug}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-6 py-4 bg-green-600 hover:bg-green-500 text-white font-bold text-base rounded-xl transition-all duration-200 hover:scale-105"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />
                </svg>
                Request via WhatsApp
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Details Section */}
      <section className="container mx-auto px-4 py-12">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
          {/* Synopsis */}
          <div className="lg:col-span-2">
            <h2 className="text-2xl font-bold text-white mb-4 border-b border-white/10 pb-3">
              Synopsis
            </h2>
            <p className="text-gray-300 leading-relaxed text-base">{movie.overview}</p>

            {/* Quality Badges */}
            <div className="mt-6 flex flex-wrap gap-3">
              {["4K UHD", "1080p HD", "Zero Ads", "No Signup", "Fast Stream"].map((tag) => (
                <span
                  key={tag}
                  className="px-4 py-2 bg-white/5 border border-white/10 text-gray-300 text-sm rounded-lg font-medium"
                >
                  ✓ {tag}
                </span>
              ))}
            </div>

            {/* Cast */}
            {movie.cast.length > 0 && (
              <div className="mt-10">
                <h2 className="text-2xl font-bold text-white mb-6 border-b border-white/10 pb-3">
                  Cast
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                  {movie.cast.map((member) => (
                    <div key={member.name} className="text-center">
                      {member.profile_path ? (
                        <img
                          src={`https://image.tmdb.org/t/p/w185${member.profile_path}`}
                          alt={member.name}
                          className="w-16 h-16 rounded-full object-cover mx-auto mb-2 border-2 border-white/10"
                          loading="lazy"
                        />
                      ) : (
                        <div className="w-16 h-16 rounded-full bg-white/10 mx-auto mb-2 flex items-center justify-center text-2xl">
                          👤
                        </div>
                      )}
                      <p className="text-white text-sm font-semibold leading-tight">{member.name}</p>
                      <p className="text-gray-500 text-xs truncate">{member.character}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar Info */}
          <div className="space-y-6">
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h3 className="text-lg font-bold text-white mb-4">Details</h3>
              <dl className="space-y-3 text-sm">
                {year && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Release Year</dt>
                    <dd className="text-gray-200 font-medium">{year}</dd>
                  </div>
                )}
                {movie.runtime > 0 && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Runtime</dt>
                    <dd className="text-gray-200 font-medium">
                      {Math.floor(movie.runtime / 60)}h {movie.runtime % 60}m
                    </dd>
                  </div>
                )}
                {movie.genres.length > 0 && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Genres</dt>
                    <dd className="text-gray-200 font-medium text-right">
                      {movie.genres.map((g) => g.name).join(", ")}
                    </dd>
                  </div>
                )}
                <div className="flex justify-between">
                  <dt className="text-gray-500">Rating</dt>
                  <dd className="text-yellow-400 font-bold">{rating} / 10</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-500">Stream Quality</dt>
                  <dd className="text-green-400 font-bold">4K / 1080p</dd>
                </div>
              </dl>
            </div>

            {/* Second CTA */}
            <a
              href={`${BASE_URL}/movie/${movie.slug}`}
              className="block w-full text-center px-6 py-4 bg-gradient-to-r from-red-600 to-red-500 text-white font-bold text-lg rounded-xl shadow-lg hover:from-red-500 hover:to-red-400 transition-all duration-200"
            >
              ▶ Stream Now — Free
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
