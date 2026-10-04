set -e
SRC="$1"
[ -f "$SRC" ] || { echo "Usage: $0 <1024x1024.png>"; exit 1; }
OUT="build/StintLab.icns"
SET="$(mktemp -d)/StintLab.iconset"
mkdir -p "$SET" build
for s in 16 32 128 256 512; do
  sips -z $s $s         "$SRC" --out "$SET/icon_${s}x${s}.png"    >/dev/null
  sips -z $((s*2)) $((s*2)) "$SRC" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$OUT"
echo "Created $OUT"