#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const args = process.argv.slice(2);

function getArg(name) {
  const index = args.indexOf(name);
  if (index < 0 || index + 1 >= args.length) {
    return "";
  }
  return args[index + 1];
}

function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const entries = {};
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const idx = line.indexOf("=");
    if (idx <= 0) {
      continue;
    }
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    entries[key] = value;
  }
  return entries;
}

function firstCsvValue(value) {
  if (!value) {
    return "";
  }
  return value
    .split(",")
    .map((part) => part.trim())
    .find((part) => part.length > 0) || "";
}

function resolveSetting(name, devEnv, prodEnv, fallback = "") {
  return process.env[name] || devEnv[name] || prodEnv[name] || fallback;
}

async function getToken(devEnv, prodEnv) {
  const tokenArg = getArg("--token");
  if (tokenArg) {
    return tokenArg;
  }

  const issuerUrl =
    getArg("--issuer-url") ||
    resolveSetting("JWT_ISSUER_URL", devEnv, prodEnv, "http://localhost:8010/token");
  const userId = getArg("--user-id") || "demo";
  const roles = (getArg("--roles") || "developer")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const workspace = getArg("--workspace") || "demo";
  const expiresInSeconds = Number.parseInt(getArg("--expires-in-seconds") || "3600", 10);
  const explicitApiVersion = getArg("--api-version");
  const apiVersion =
    explicitApiVersion ||
    firstCsvValue(resolveSetting("JWT_ALLOWED_API_VERSIONS", devEnv, prodEnv, ""));
  const issuerAdminToken =
    getArg("--issuer-admin-token") || resolveSetting("JWT_ISSUER_ADMIN_TOKEN", devEnv, prodEnv, "");

  const body = {
    user_id: userId,
    roles,
    workspace,
    expires_in_seconds: Number.isFinite(expiresInSeconds) ? expiresInSeconds : 3600,
  };
  if (apiVersion) {
    body.api_version = apiVersion;
  }

  const headers = {
    "Content-Type": "application/json",
  };
  if (issuerAdminToken) {
    headers["X-Issuer-Token"] = issuerAdminToken;
  }

  const response = await fetch(issuerUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const details = payload ? JSON.stringify(payload) : response.statusText;
    throw new Error(`Token issuer request failed (${response.status}): ${details}`);
  }

  const token = typeof payload?.access_token === "string" ? payload.access_token.trim() : "";
  if (!token) {
    throw new Error("Token issuer response missing access_token");
  }
  return token;
}

let buffer = Buffer.alloc(0);
let requestChain = Promise.resolve();
let endpoint = "";
let token = "";
let resolveBridgeReady;
let rejectBridgeReady;
const bridgeReady = new Promise((resolve, reject) => {
  resolveBridgeReady = resolve;
  rejectBridgeReady = reject;
});

function writeMessage(message) {
  // VS Code MCP stdio expects newline-delimited JSON-RPC messages.
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function makeErrorResponse(id, code, message, data) {
  return {
    jsonrpc: "2.0",
    id: id ?? null,
    error: {
      code,
      message,
      data,
    },
  };
}

function parseContentLength(headerText) {
  const lines = headerText.split(/\r?\n/);
  for (const line of lines) {
    const idx = line.indexOf(":");
    if (idx < 0) {
      continue;
    }
    const key = line.slice(0, idx).trim().toLowerCase();
    const value = line.slice(idx + 1).trim();
    if (key === "content-length") {
      const parsed = Number.parseInt(value, 10);
      return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
    }
  }
  return null;
}

function findHeaderEnd(buf) {
  const crlf = buf.indexOf("\r\n\r\n", 0, "utf8");
  const lf = buf.indexOf("\n\n", 0, "utf8");

  if (crlf < 0 && lf < 0) {
    return null;
  }
  if (crlf < 0) {
    return { index: lf, size: 2 };
  }
  if (lf < 0) {
    return { index: crlf, size: 4 };
  }
  if (crlf < lf) {
    return { index: crlf, size: 4 };
  }
  return { index: lf, size: 2 };
}

async function forwardRequest(request) {
  const requestId = request?.id;
  const isNotification = requestId === undefined || requestId === null;

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      body: JSON.stringify(request),
    });

    const rawText = await response.text();
    let parsed = null;
    if (rawText) {
      try {
        parsed = JSON.parse(rawText);
      } catch {
        parsed = rawText;
      }
    }

    if (!response.ok) {
      if (!isNotification) {
        writeMessage(
          makeErrorResponse(
            requestId,
            -32000,
            `HTTP ${response.status}: ${response.statusText}`,
            parsed
          )
        );
      }
      return;
    }

    if (isNotification || parsed === null || parsed === "") {
      return;
    }

    if (typeof parsed === "object" && parsed.jsonrpc === "2.0" && ("result" in parsed || "error" in parsed)) {
      writeMessage({
        ...parsed,
        id: requestId,
      });
      return;
    }

    writeMessage({
      jsonrpc: "2.0",
      id: requestId,
      result: parsed,
    });
  } catch (error) {
    if (!isNotification) {
      writeMessage(
        makeErrorResponse(
          requestId,
          -32603,
          error instanceof Error ? error.message : "Bridge request failed",
          null
        )
      );
    }
  }
}

function enqueuePayload(payloadText) {
  let request;
  try {
    request = JSON.parse(payloadText);
  } catch (error) {
    writeMessage(
      makeErrorResponse(
        null,
        -32700,
        "Invalid JSON-RPC request",
        error instanceof Error ? error.message : "Parse error"
      )
    );
    return;
  }
  requestChain = requestChain
    .then(() => bridgeReady)
    .then(() => forwardRequest(request));
}

function processBuffer() {
  while (true) {
    if (buffer.length === 0) {
      return;
    }

    const prefix = buffer
      .slice(0, Math.min(buffer.length, 32))
      .toString("utf8")
      .trimStart()
      .toLowerCase();

    if (!prefix.startsWith("content-length:")) {
      const newlineIndex = buffer.indexOf(0x0a);
      if (newlineIndex < 0) {
        return;
      }

      const line = buffer
        .slice(0, newlineIndex)
        .toString("utf8")
        .replace(/\r$/, "")
        .trim();
      buffer = buffer.slice(newlineIndex + 1);

      if (!line) {
        continue;
      }

      enqueuePayload(line);
      continue;
    }

    const headerMeta = findHeaderEnd(buffer);
    if (!headerMeta) {
      return;
    }

    const headerEnd = headerMeta.index;
    const headerText = buffer.slice(0, headerEnd).toString("utf8");
    const contentLength = parseContentLength(headerText);
    if (contentLength === null) {
      buffer = buffer.slice(headerEnd + headerMeta.size);
      writeMessage(makeErrorResponse(null, -32600, "Missing or invalid Content-Length header", null));
      continue;
    }

    const messageStart = headerEnd + headerMeta.size;
    const messageEnd = messageStart + contentLength;
    if (buffer.length < messageEnd) {
      return;
    }

    const payloadText = buffer.slice(messageStart, messageEnd).toString("utf8");
    buffer = buffer.slice(messageEnd);
    enqueuePayload(payloadText);
  }
}

process.stdin.on("data", (chunk) => {
  const incoming = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk, "utf8");
  buffer = Buffer.concat([buffer, incoming]);
  processBuffer();
});

process.stdin.on("end", () => {
  processBuffer();
});

async function main() {
  const workspaceRoot = path.resolve(__dirname, "..");
  const devEnv = readEnvFile(path.join(workspaceRoot, ".env.development"));
  const prodEnv = readEnvFile(path.join(workspaceRoot, ".env"));

  endpoint =
    getArg("--endpoint") ||
    resolveSetting("MCP_GATEWAY_SSE_ENDPOINT", devEnv, prodEnv, "http://localhost:8000/sse");
  if (!endpoint) {
    throw new Error("Missing --endpoint and MCP_GATEWAY_SSE_ENDPOINT");
  }

  token = await getToken(devEnv, prodEnv);
  console.error("Starting MCP bridge with freshly issued JWT...");
  resolveBridgeReady();
}

main().catch((error) => {
  rejectBridgeReady(error);
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
