// Copy React and ReactDOM UMD builds from node_modules into ./vendor so the app can run offline.
// Usage: node scripts/download-umd.js
// Allows override: set SKIP_UMD_INTEGRITY=1 to bypass size check.

const fs = require('fs');
const path = require('path');

const files = [
  {
    src: path.join(__dirname, '..', 'node_modules', 'react', 'umd', 'react.production.min.js'),
    dest: path.join(__dirname, '..', 'vendor', 'react.production.min.js')
  },
  {
    src: path.join(__dirname, '..', 'node_modules', 'react-dom', 'umd', 'react-dom.production.min.js'),
    dest: path.join(__dirname, '..', 'vendor', 'react-dom.production.min.js')
  }
];

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function copyWithIntegrity(src, dest) {
  if (!fs.existsSync(src)) throw new Error(`Missing source: ${src}`);
  fs.copyFileSync(src, dest);
  let stat = fs.statSync(dest);
  const isReactDom = dest.includes('react-dom');
  if (process.env.SKIP_UMD_INTEGRITY === '1') {
    console.log(`[skip integrity] ${path.basename(dest)} size=${stat.size}`);
    return;
  }
  const minSize = isReactDom ? 80000 : 30000; // thresholds
  if (stat.size < minSize && !isReactDom) {
    // Attempt fallback to development build for react (not for react-dom to avoid huge bundle if only dom file is broken)
    const devSrc = src.replace('react.production.min.js', 'react.development.js');
    if (fs.existsSync(devSrc)) {
      console.warn(`[warn] Production React appears truncated (size=${stat.size}). Falling back to development build: ${devSrc}`);
      fs.copyFileSync(devSrc, dest);
      stat = fs.statSync(dest);
    } else {
      console.warn(`[warn] Production React truncated and development build not found at ${devSrc}`);
    }
  }
  if (stat.size < minSize) {
    console.warn(`[warn] ${path.basename(dest)} size still below expected threshold (${stat.size} < ${minSize}). Application may fail. Set SKIP_UMD_INTEGRITY=1 to ignore.`);
  }
  console.log(`Saved ${dest} (size=${stat.size})`);
}

async function main() {
  try {
    const vendorDir = path.join(__dirname, '..', 'vendor');
    ensureDir(vendorDir);
    for (const f of files) {
      console.log('Copying', f.src, '->', f.dest);
      copyWithIntegrity(f.src, f.dest);
    }
    console.log('All files copied to vendor/');
  } catch (err) {
    console.error('Prepare failed:', err && err.message);
    process.exit(1);
  }
}

if (require.main === module) main();
