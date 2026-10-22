# Input assets, reuse and private fixtures

## Included artwork

The package includes the five generated dog illustrations from this conversation and the most recent five-dog cream collage. These preserve the requested visual direction without depending on conversation image history.

| Package path | Role |
|---|---|
| `assets/style/dog-watercolor-transparent.png` | Primary pencil/watercolor style reference; original small white dog. |
| `assets/portraits/dog-01-black-watercolor-transparent.png` | Existing generated black-dog illustration. |
| `assets/portraits/dog-02-curly-watercolor-transparent.png` | Existing generated curly-coat illustration. |
| `assets/portraits/dog-03-black-white-watercolor-transparent.png` | Existing generated black-and-white illustration. |
| `assets/portraits/dog-04-golden-watercolor-transparent.png` | Existing generated golden-dog illustration. |
| `assets/examples/five-dogs-collage-cream-1920x1080.png` | Approved composition direction: cream, landscape, scattered portraits. |
| `assets/prompts/` | Existing generation prompts, preserved as historical reference text. |
| `reference/extract_video_frames.py.txt` | Existing generic frame-extraction script copied as non-executable reference text. |

[ASSET_MANIFEST.json](../ASSET_MANIFEST.json) records original locations, roles, dimensions and hashes. [SHA256SUMS](../SHA256SUMS) covers the delivered package. The package manifest does not turn illustration filenames into verified physical identities.

Use the primary style reference to implement a reusable prompt template. Inspect the other illustrations and collage to understand outline delicacy, muted pigment, paper-like interior texture, full-body treatment and proportions. Avoid baking one dog's appearance into every prompt. Test large exterior alpha areas and dark/cream compositing; faint edge alpha can be normal antialiasing.

The five artwork files are useful render fixtures. They are **not** real camera observations, encoder enrollment data, ground truth for matching, or independent returning-dog examples. Generated anatomy or markings must not be fed back as recognition evidence.

## Existing source videos

Private videos are **not bundled**. These paths are known attachment locations on the original Windows host. Availability must be checked; they are not CT112 paths, network URLs or permanent storage guarantees.

Shared attachment root:

~~~text
C:/Users/Sam/.codex/codex-remote-attachments/
01a15b00-30f7-7850-8b01-d1f7b4ed922a/
~~~

The two lines above form one directory path. Append the following relative suffixes:

| Visual reference | Relative suffix |
|---|---|
| Small white dog | `F492FFDA-994F-49F2-9351-0115F3F468A2/1-1792678192.821723-40hh1a.mp4` |
| Black short-coat dog | `13450D4D-683E-44E5-B46C-9413345A39AB/1-1792672686.145351-2g4wz6.mp4` |
| Curly-coat dog | `13450D4D-683E-44E5-B46C-9413345A39AB/2-1792669065.122732-yr0l4y.mp4` |
| Black-and-white dog | `13450D4D-683E-44E5-B46C-9413345A39AB/3-1792666653.806317-egd9g6.mp4` |
| Golden dog | `13450D4D-683E-44E5-B46C-9413345A39AB/4-1792621194.489406-rf85ux.mp4` |

These appearance labels describe the earlier artistic workflow, not a claim that all five identities have been independently verified. The five clips alone cannot establish recognition performance across independent return visits.

## Existing local extraction work

The authoring workspace is:

~~~text
C:/Users/Sam/Documents/Codex/2026-10-20/grab-the-image-at-https-cdn
~~~

Reusable material there includes:
- `.tools/extract_video_frames.py`: generic video/output arguments, FFmpeg-backed frame sampling, metadata and contact sheets.
- `source/dog-video-frames/` and `source/dog-reference-01.png` / `source/dog-reference-04.png`: earlier white-dog frames/crops.
- `source/video-2g4wz6/`, `source/video-yr0l4y/`, `source/video-egd9g6/`, `source/video-rf85ux/`: contact sheets and selected references for the other dogs.
- `output/`: generated artwork and saved prompt text included in this package.

The frame-extraction script used the authoring workspace's bundled tools. Its path assumptions and manually selected crops are not a production design. Inspect and adapt the frame/decode approach after verifying target dependencies; add track-based selection, native-resolution crop mapping, bounds, timestamps and quality handling. Do not run its text copy as a production service or copy bundled Windows dependency paths onto Debian.

No generated artwork is being edited or regenerated as part of this documentation delivery.

## Future private-fixture staging

During an explicitly launched build:
1. Inspect available attachments and Frigate recordings through authorized read-only routes.
2. Select the minimum useful private sample; preserve the originals.
3. Copy into an ignored, application-owned private fixture directory on the executing host/CT112 with restrictive permissions. Record checksum, source event, camera, timestamp and consent/scope provenance.
4. Label independent physical visits and difficult negative examples. Keep labels distinguishable from model predictions.
5. Keep real clips/crops out of Git, release archives, public issue reports and cloud test fixtures.
6. Use synthetic redacted events and included generated art for public/default tests. Tests needing private data must say so and must not report a skip as a pass.
7. If clips have expired or independent returns are unavailable, record the missing evidence, complete offline/shadow work and request a narrowly specified data/access decision.

The production application must obtain its own verified event-time crops. It must not rely on the continued presence of this Windows attachment directory.

