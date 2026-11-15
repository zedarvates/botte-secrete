# YuE2 weights: source qualification

Status: **dated evidence, 13 September 2026; source review completed with a
negative commercial-use decision**. This records a candidate assessment for
Botte Secrète PR #118, not selection of a production music provider.

For the intended commercial music workflow, keep these YuE2 checkpoints excluded
unless separate applicable permission is established. The published weight
licence is CC BY-NC 4.0. The remaining external evidence is that permission,
not another declaration-guard test or another review of the same notices.

## Sources and component boundaries

The reviewed first-party source revision is
[`88da114a67df892af0329472073b96a5ef700b93`](https://github.com/multimodal-art-projection/YuE/tree/88da114a67df892af0329472073b96a5ef700b93).
Its [README](https://github.com/multimodal-art-projection/YuE/blob/88da114a67df892af0329472073b96a5ef700b93/README.md)
distinguishes the following scopes:

| Component | Published terms / scope | Review consequence |
|---|---|---|
| Current first-party code, skill and documentation | [Apache-2.0](https://github.com/multimodal-art-projection/YuE/blob/88da114a67df892af0329472073b96a5ef700b93/LICENSE) | Assess applicable code and notice obligations separately from weights |
| YuE2-3B, YuE2-Vae and YuE2-Vae-legacy `model.safetensors` | [CC BY-NC 4.0](https://github.com/multimodal-art-projection/YuE/blob/88da114a67df892af0329472073b96a5ef700b93/MODEL_LICENSE) | No commercial promotion on these published terms alone |
| Identified Oobleck/stable-audio-tools and SnakeBeta/BigVGAN source | [Retained MIT notices](https://github.com/multimodal-art-projection/YuE/blob/88da114a67df892af0329472073b96a5ef700b93/THIRD_PARTY_NOTICES.md) | The source notices do not relicense checkpoint weights |
| Earlier release archives, original YuE, tokenization files and other assets | Separate scope or bundled terms | Do not extend the current source licence to uninspected material |

The [pipeline source](https://github.com/multimodal-art-projection/YuE/blob/88da114a67df892af0329472073b96a5ef700b93/src/yue2/pipeline.py)
defaults to **YuE2-3B plus YuE2-Vae** and accepts separate `revision` and
`vae_revision` arguments. The README identifies **YuE2-Vae-legacy** as the decoder
for its reported benchmark protocol. A future source record must identify the
decoder as well as the generation model. Their results are not interchangeable.
The README states that a separate MERT2 model download is optional for generation;
cover/transcription workflows are outside this review.

## Pinned checkpoint repositories

Only Git metadata and text were inspected in bare repositories, with no checkout,
LFS download, package installation or model loading. Each pinned repository's
README declares `cc-by-nc-4.0`; each `LICENSE` explicitly scopes the three named
checkpoint weights. These are publisher declarations, not independent attestations.

| Model | Role | Inspected repository revision | Weight licence |
|---|---|---|---|
| YuE2-3B | Generation model | `29b3558dd46954a0cd9021dc76d5c91864a0f1c7` | [LICENSE](https://huggingface.co/m-a-p/YuE2-3B/blob/29b3558dd46954a0cd9021dc76d5c91864a0f1c7/LICENSE) |
| YuE2-Vae | Default generation/listening decoder | `9a94e1d0ea9f8087e98f77fa88df4a4068104d2a` | [LICENSE](https://huggingface.co/m-a-p/YuE2-Vae/blob/9a94e1d0ea9f8087e98f77fa88df4a4068104d2a/LICENSE) |
| YuE2-Vae-legacy | Reported benchmark decoder | `5ddd12f79acb90d24b3a672dcd2ebf88da7c92a9` | [LICENSE](https://huggingface.co/m-a-p/YuE2-Vae-legacy/blob/5ddd12f79acb90d24b3a672dcd2ebf88da7c92a9/LICENSE) |

The three inspected Hugging Face `LICENSE` files are byte-identical: Git blob
`5b4b50fd3e4d4cadbc54c49cab3552d0eb303d48`, SHA-256
`060985741d20e70613b4c189c7de106cabd3fb2109fbbfb6d705c9d619417dd0`.
The [weight licence text](https://huggingface.co/m-a-p/YuE2-3B/blob/29b3558dd46954a0cd9021dc76d5c91864a0f1c7/LICENSE)
includes CC BY-NC 4.0 sections 1(i), 2(a) and 6(c): the non-commercial definition,
the limited grants and the possibility of separate terms. This review does not
establish a separate grant or adjudicate any exception.

## Published weight identities

For each revision above, the SHA-256 and byte count in `weights_manifest.json`
match the `oid sha256` and `size` of the Git LFS pointer at `model.safetensors`.
The values below identify **publisher-advertised weight content**; they were not
recalculated from checkpoint bytes.

| Model | Published SHA-256 of `model.safetensors` | Published bytes | Pinned manifest |
|---|---|---:|---|
| YuE2-3B | `1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9` | 7261441640 | [Manifest](https://huggingface.co/m-a-p/YuE2-3B/blob/29b3558dd46954a0cd9021dc76d5c91864a0f1c7/weights_manifest.json) |
| YuE2-Vae | `807ce9d5149fa27c5ad3e6582058469852e908f6c5acc8c8aa338e7ab7751346` | 530512720 | [Manifest](https://huggingface.co/m-a-p/YuE2-Vae/blob/9a94e1d0ea9f8087e98f77fa88df4a4068104d2a/weights_manifest.json) |
| YuE2-Vae-legacy | `b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044` | 530512720 | [Manifest](https://huggingface.co/m-a-p/YuE2-Vae-legacy/blob/5ddd12f79acb90d24b3a672dcd2ebf88da7c92a9/weights_manifest.json) |

The default and legacy VAE have the same published size but different digests.
Metadata agreement from one publisher is not an independent integrity check.
Any later, separately justified acquisition would need to verify the acquired
bytes against these identities before reporting them as verified artifacts.

## Decision and stopping boundary

The source-qualification gap is closed **with a blocking finding**: the reviewed
generation model and both decoders carry non-commercial weight terms. No separate
commercial permission was supplied or established in this review. Keep this
candidate out of the intended commercial path until an applicable grant covers
the actual generation model and selected decoder. A differently licensed
candidate would require its own source qualification.

The [declaration guard](../skills/execution_harness/contract.py) rejects the
declared `CC-BY-NC-4.0` for commercial use. Its return without an exception for
another string, including a custom licence, cannot supply missing permission.

This is not a complete runtime dependency audit or a rights assessment for
generated music, input songs, lyrics, performances or other assets. It proves no
music quality, throughput or GPU/homelab compatibility. Those questions do not
justify downloading or executing this blocked candidate in this slice.

No rights-holder message was sent. No checkpoint bytes were downloaded or hashed,
and no inference was run. Atlas persistence, automatic routing, activation and
merging remain out of scope. The frozen Needle/Qwen study and its seed are
unaffected by this documentary review.
