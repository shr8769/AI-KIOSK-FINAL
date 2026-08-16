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
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const resolvedParams = await params;
    const id = resolvedParams.id;

    const backendBaseUrl = (process.env.BACKEND_API_BASE_URL || process.env.NEXT_PUBLIC_BACKEND_URL || process.env.PUBLIC_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
    if (backendBaseUrl) {
      try {
        const backendRes = await fetch(`${backendBaseUrl}/navigation/${id}`, {
          cache: 'no-store',
          headers: { Accept: 'application/json' },
          signal: AbortSignal.timeout(2000)
        });

        if (backendRes.ok) {
          const backendJson = await backendRes.json();
          const payload = normalizePayload(backendJson);
          return NextResponse.json({ status: 'success', data: payload });
        }
      } catch (backendError) {
        console.warn('Falling back to Upstash for navigation route:', backendError);
      }
    }

    if (!redis) {
      return NextResponse.json(
        { error: 'Upstash Redis is not configured on this deployment' },
        { status: 500 }
      );
    }

    const data = await redis.get(`nav:${id}`);

    if (!data) {
      return NextResponse.json(
        { error: 'Navigation route not found or has expired' },
        { status: 404 }
      );
    }

    const payload = normalizePayload(typeof data === 'string' ? JSON.parse(data) : data);

    return NextResponse.json({ status: 'success', data: payload });
  } catch (error) {
    console.error('Error fetching navigation route:', error);
    return NextResponse.json(
      { error: 'Internal server error while retrieving route' },
      { status: 500 }
    );
  }
}
