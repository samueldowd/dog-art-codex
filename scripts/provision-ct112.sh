#!/bin/sh
# Runtime provisioning is deliberately separate from the release archive.
# Usage: sudo sh provision-ct112.sh /home/chatgpt/dog-art-build
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Interactive sudo required'; exit 1; }
[ "$(hostname)" = CT112 ] || { echo 'Wrong target hostname'; exit 1; }
[ "$#" -eq 1 ] || { echo 'Protected staging directory required'; exit 1; }
staging=$(realpath "$1")
[ -d "$staging" ] && [ ! -L "$1" ]
for p in /etc/dog-art /var/lib/dog-art; do [ -d "$p" ] && [ ! -L "$p" ]; done
(cd "$staging/models" && printf '%s\n' \
 'f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a  dinov2-small.onnx' \
 'c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d  yolox_nano.onnx' | sha256sum -c -)
if [ ! -e /etc/dog-art/.env ]; then
 [ -f "$staging/runtime.env" ] && [ ! -L "$staging/runtime.env" ]
 install -o root -g dog-art -m 0640 "$staging/runtime.env" /etc/dog-art/.env
else
 echo 'Preserving existing runtime secrets file.'
fi
install -d -o dog-art -g dog-art -m 0700 /var/lib/dog-art/models
for file in dinov2-small.onnx yolox_nano.onnx encoder.json detector.json; do
 [ -f "$staging/models/$file" ] && [ ! -L "$staging/models/$file" ]
 [ ! -e "/var/lib/dog-art/models/$file" ] || { echo 'Model exists; inspect before replacing'; exit 1; }
 install -o dog-art -g dog-art -m 0600 "$staging/models/$file" "/var/lib/dog-art/models/$file"
done
printf '%s\n' 'Runtime secrets and pinned local models provisioned; no services started.'
