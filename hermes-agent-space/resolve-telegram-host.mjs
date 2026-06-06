#!/usr/bin/env node
import dns from "node:dns/promises";
import fs from "node:fs";
import tls from "node:tls";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const host = process.env.OPENCLAW_TELEGRAM_API_HOST?.trim() || "api.telegram.org";
const resolvers = ["1.1.1.1", "8.8.8.8"];
const hostsPath = "/etc/hosts";
const knownTelegramIps = [
  "149.154.166.110",
  "149.154.167.220",
  "149.154.167.99",
  "149.154.167.91",
  "149.154.167.92",
  "149.154.167.50",
  "149.154.164.250",
];

function dedupe(values) {
  return [...new Set(values.filter(Boolean))];
}

async function fromLocalDns() {
  const results = await dns.lookup(host, { family: 4, all: true });
  return results.map((entry) => entry.address);
}

async function fromNslookup(server) {
  const { stdout } = await execFileAsync("nslookup", [host, server], { timeout: 10000 });
  return stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^\d+\.\d+\.\d+\.\d+$/.test(line))
    .filter((ip) => ip !== server);
}

async function fromGoogleDnsJson() {
  const { stdout } = await execFileAsync(
    "curl",
    [
      "--silent",
      "--show-error",
      "--max-time",
      "15",
      "https://dns.google/resolve?name=" + host + "&type=A",
    ],
    { timeout: 20000 },
  );
  const data = JSON.parse(stdout || "null");
  return (data?.Answer || [])
    .map((record) => record?.data)
    .filter((value) => /^\d+\.\d+\.\d+\.\d+$/.test(value || ""));
}

async function collectIps() {
  const results = [];

  for (const task of [
    { name: "local-dns", run: fromLocalDns },
    ...resolvers.map((server) => ({
      name: `nslookup-${server}`,
      run: () => fromNslookup(server),
    })),
    { name: "dns-google-json", run: fromGoogleDnsJson },
  ]) {
    try {
      const ips = dedupe(await task.run());
      console.log(`[openclaw-telegram-hosts] source=${task.name} status=${ips.length > 0 ? "ok" : "miss"} ips=${ips.join(",") || "-"}`);
      results.push(...ips);
    } catch (error) {
      console.log(
        `[openclaw-telegram-hosts] source=${task.name} status=miss reason=${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
  }

  return dedupe([
    ...results,
    ...parseEnvIps(),
    ...knownTelegramIps,
  ]);
}

function parseEnvIps() {
  return (process.env.OPENCLAW_TELEGRAM_API_IPS?.trim() || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function canHandshake(ip) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const socket = tls.connect(
      {
        host: ip,
        port: 443,
        servername: host,
        rejectUnauthorized: true,
      },
      () => {
        socket.end();
        finish(true);
      },
    );
    socket.setTimeout(5000, () => socket.destroy());
    socket.on("error", () => finish(false));
    socket.on("close", () => finish(false));
  });
}

async function main() {
  const ips = await collectIps();
  if (ips.length === 0) {
    console.warn(`[openclaw-telegram-hosts] no IPv4 addresses resolved for ${host}`);
    return;
  }

  let selectedIp = "";
  for (const ip of ips) {
    const ok = await canHandshake(ip);
    console.log(`[openclaw-telegram-hosts] probe ip=${ip} tls443=${ok ? "ok" : "failed"}`);
    if (ok) {
      selectedIp = ip;
      break;
    }
  }

  if (!selectedIp) {
    selectedIp = ips[0];
    console.warn(`[openclaw-telegram-hosts] no reachable IP found; falling back to first candidate ${selectedIp}`);
  }

  const hostsRaw = fs.readFileSync(hostsPath, "utf8");
  const filtered = hostsRaw
    .split(/\r?\n/)
    .filter((line) => !line.includes(` ${host}`) && !line.endsWith(`\t${host}`));
  const next = `${filtered.join("\n").trim()}\n${selectedIp} ${host}\n`;
  fs.writeFileSync(hostsPath, next, "utf8");
  console.log(`[openclaw-telegram-hosts] mapped ${host} -> ${selectedIp} in ${hostsPath}`);
}

await main();
