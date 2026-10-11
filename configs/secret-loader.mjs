import { readFileSync } from "node:fs";

let values;
try {
  values = JSON.parse(readFileSync(new URL("./env.json", import.meta.url), "utf8"));
} catch {
  throw new Error("Cannot load secret JSON");
}
if (values === null || typeof values !== "object" || Array.isArray(values)) {
  throw new Error("Invalid secret entries");
}
for (const [name, value] of Object.entries(values)) {
  if (!/^[A-Z][A-Z0-9_]*$/.test(name) || typeof value !== "string") {
    throw new Error("Invalid secret entry");
  }
  if (process.env[name] !== undefined && process.env[name] !== value) {
    throw new Error(`Conflicting secret: ${name}`);
  }
  process.env[name] = value;
}
