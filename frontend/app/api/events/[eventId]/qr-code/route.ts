import { NextRequest, NextResponse } from 'next/server';
import { headers } from 'next/headers';

/**
 * Proxy the QR code PNG from the backend.
 * Avoids CORS issues by serving it through the Next.js origin.
 * Forwards the Authorization header from the incoming request if present.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { eventId: string } }
) {
  const { eventId } = params;
  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const targetUrl = `${backendUrl}/api/v1/events/${eventId}/qr-code`;

  // Forward auth header if the client sent one
  const incomingHeaders = headers();
  const authHeader = incomingHeaders.get('authorization');

  const fetchHeaders: Record<string, string> = {};
  if (authHeader) {
    fetchHeaders['Authorization'] = authHeader;
  }

  try {
    const backendRes = await fetch(targetUrl, { headers: fetchHeaders });
    if (!backendRes.ok) {
      return NextResponse.json(
        { detail: 'Failed to fetch QR code from backend' },
        { status: backendRes.status }
      );
    }

    const imageBytes = await backendRes.arrayBuffer();
    return new NextResponse(imageBytes, {
      status: 200,
      headers: {
        'Content-Type': 'image/png',
        'Cache-Control': 'no-store',
      },
    });
  } catch {
    return NextResponse.json(
      { detail: 'Backend unavailable' },
      { status: 502 }
    );
  }
}
