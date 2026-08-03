import { NextResponse } from 'next/server';
import { Redis } from '@upstash/redis';

const redis = (process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN)
  ? new Redis({
      url: process.env.UPSTASH_REDIS_REST_URL,
      token: process.env.UPSTASH_REDIS_REST_TOKEN,
    })
  : null;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const resolvedParams = await params;
    const id = resolvedParams.id;
    
    if (!redis) {
      // Fallback to local FastAPI backend for local development/testing
      try {
        const backendRes = await fetch(`http://127.0.0.1:8000/api/v1/navigation/${id}`);
        if (backendRes.ok) {
           const data = await backendRes.json();
           // The backend returns { status: "success", data: session_payload }
           return NextResponse.json(data.data);
        }
      } catch (e) {
        console.warn('Local backend fallback failed:', e);
      }
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

    const payload = typeof data === 'string' ? JSON.parse(data) : data;

    return NextResponse.json(payload);
  } catch (error) {
    console.error('Error fetching navigation route from Upstash:', error);
    return NextResponse.json(
      { error: 'Internal server error while retrieving route' },
      { status: 500 }
    );
  }
}
