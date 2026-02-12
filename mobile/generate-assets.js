// Run: node generate-assets.js
// Creates placeholder icon/splash PNGs (solid color with N)
const fs = require('fs');

// Minimal 1x1 purple PNG for placeholders (real icons should be designed)
// This creates a valid PNG that Expo can use
const { createCanvas } = (() => {
  try { return require('canvas'); } catch(e) { return { createCanvas: null }; }
})();

if (!createCanvas) {
  // Create minimal valid PNGs without canvas
  // 1x1 pixel purple PNG
  const pixel = Buffer.from(
    '89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d76360f8cf800000000201012718e9060000000049454e44ae426082',
    'hex'
  );
  
  fs.writeFileSync('assets/icon.png', pixel);
  fs.writeFileSync('assets/adaptive-icon.png', pixel);
  fs.writeFileSync('assets/notification-icon.png', pixel);
  fs.writeFileSync('assets/splash.png', pixel);
  console.log('Created placeholder PNGs (1x1 pixel). Replace with real assets for production.');
} else {
  // Create proper icons with canvas
  const sizes = { 'assets/icon.png': 1024, 'assets/adaptive-icon.png': 1024, 'assets/splash.png': 1284, 'assets/notification-icon.png': 96 };
  
  for (const [file, size] of Object.entries(sizes)) {
    const canvas = createCanvas(size, size);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = '#8b5cf6';
    ctx.font = `bold ${size * 0.5}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('N', size / 2, size / 2);
    fs.writeFileSync(file, canvas.toBuffer('image/png'));
    console.log(`Created ${file} (${size}x${size})`);
  }
}
