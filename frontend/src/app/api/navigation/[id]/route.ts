import { NextResponse } from 'next/server';
import { Redis } from '@upstash/redis';

const redis = (process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN)
  ? new Redis({
      url: process.env.UPSTASH_REDIS_REST_URL,
      token: process.env.UPSTASH_REDIS_REST_TOKEN,
    })
  : null;

function normalizePayload(payload: unknown) {
  if (!payload || typeof payload !== 'object') return payload;

  const record = payload as Record<string, unknown>;
  if ('data' in record && record.data !== undefined) {
    return record.data;
  }

  return payload;
}

export async function GET(
  request: Request,
  { params }: { params: any }
) {
  try {
    const resolvedParams = (await Promise.resolve(params)) as { id?: string } | undefined;
    const id = resolvedParams?.id;

    if (!id) {
      return NextResponse.json({ error: 'Navigation ID missing' }, { status: 400 });
    }

    const backendBaseUrl = (
      process.env.BACKEND_API_BASE_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      'http://127.0.0.1:8000/api/v1'
    ).replace(/\/$/, '');

    if (backendBaseUrl) {
      try {
        const backendRes = await fetch(`${backendBaseUrl}/navigation/${id}`, {
          cache: 'no-store',
          headers: { Accept: 'application/json' },
          signal: AbortSignal.timeout(3000)
        });

        if (backendRes.ok) {
          const backendJson = await backendRes.json();
          const payload = normalizePayload(backendJson);
          return NextResponse.json({ status: 'success', data: payload });
        } else if (backendRes.status === 404) {
          // Check disk store before giving up
        }
      } catch (backendError) {
        console.warn('FastAPI backend fetch error, checking fallback:', backendError);
      }
    }

    // 2. Local disk store fallback (instant, offline-capable)
    try {
      const fs = await import('fs');
      const path = await import('path');
      const diskPaths = [
        path.resolve(process.cwd(), '..', 'data', 'navigation_sessions.json'),
        path.resolve(process.cwd(), 'data', 'navigation_sessions.json'),
        'C:\\AI-KIOSK\\data\\navigation_sessions.json'
      ];
      for (const dp of diskPaths) {
        if (fs.existsSync(dp)) {
          const diskData = JSON.parse(fs.readFileSync(dp, 'utf-8'));
          if (diskData && diskData[id]) {
            return NextResponse.json({ status: 'success', data: diskData[id] });
          }
        }
      }
    } catch (diskErr) {
      console.warn('Error reading disk navigation store:', diskErr);
    }

    if (!redis) {
      return NextResponse.json(
        { error: 'Navigation session not found on server' },
        { status: 404 }
      );
    }

    const data = await redis.get(`nav:${id}`);

    if (!data) {
      return NextResponse.json(
        { error: 'Navigation route not found or has expired' },
        { status: 404 }
      );
    }

    const payload = normalizePayload(typeof data === 'string' ? jsonParseSafe(data) : data);
    return NextResponse.json({ status: 'success', data: payload });
  } catch (error) {
    console.error('Error fetching navigation route:', error);
    return NextResponse.json(
      { error: 'Internal server error while retrieving route' },
      { status: 500 }
    );
  }
}

function jsonParseSafe(str: string) {
  try {
    return JSON.parse(str);
  } catch {
    return str;
  }
}
