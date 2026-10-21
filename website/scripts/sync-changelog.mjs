// Copies the repository CHANGELOG into the site (the site is deployed from this folder alone; the copy is committed).
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../../CHANGELOG.md");
const target = resolve(here, "../content/changelog.md");
if (existsSync(source)) {
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
  console.log("changelog synced");
} else {
  console.log("changelog: using the committed copy");
}
