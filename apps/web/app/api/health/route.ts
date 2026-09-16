import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({
    status: "ok",
    service: "gridshift-web",
    version: process.env.APP_VERSION ?? "0.1.0",
    timestamp: new Date().toISOString(),
  });
}
