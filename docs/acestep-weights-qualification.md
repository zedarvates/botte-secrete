# ACE-Step 1.5: source qualification for a request preview

Status: **dated evidence and bounded proposal, 13 September 2026**.
The published licence declarations support preparing a non-executing request
adapter for one ACE-Step 1.5 profile. This is a candidate assessment, not a
production-provider selection or approval to run a model. The separate
[YuE2 blocking finding](yue2-weights-qualification.md) remains unchanged.

## Reviewed sources and licence scope

| Source | Pinned revision | Evidence and consequence |
|---|---|---|
| `ace-step/ACE-Step-1.5` source | `ca1e85fe9430179831e6bc6be790c332190a3866` | [MIT source licence](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/LICENSE); preserve the required copyright and permission notices |
| `ACE-Step/Ace-Step1.5` model bundle | `19671f406d603126926c1b7e2adc169acbcade22` | [Publisher model card](https://huggingface.co/ACE-Step/Ace-Step1.5/blob/19671f406d603126926c1b7e2adc169acbcade22/README.md) declares MIT and states commercial use of generated music is intended |
| `Qwen/Qwen3-Embedding-0.6B` upstream | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | [Qwen model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3/README.md) declares Apache-2.0; retain those separate terms for the bundled encoder |

The two HF repositories have no separate `LICENSE` file at these revisions;
their model cards are the publisher declarations reviewed here. Neither the
ACE-Step card's dataset-rights statements nor its output-rights claims were
independently verified. The bundle's MIT label does not relicense Qwen material.
Any future redistribution must preserve the applicable MIT notices and
[Apache-2.0 conditions](https://www.apache.org/licenses/LICENSE-2.0), including
licence, modification and attribution/NOTICE obligations where applicable.
No non-commercial restriction was identified in these declared terms. This
licence screen is not a complete dependency, training-data or output-rights audit.

## Minimal candidate profile

The reviewed profile is `acestep-v15-turbo` (the 2B family), the bundled
`official` VAE, Qwen3-Embedding-0.6B and the DiT's silence-latent asset, with no
5Hz planner LM. It excludes XL, community VAEs, LoRA, covers and reference audio.

The pinned [component loader](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/init_service_loader_components.py)
loads the official `vae` directory and the `Qwen3-Embedding-0.6B` directory.
The [DiT loader](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/init_service_loader.py)
also requires `acestep-v15-turbo/silence_latent.pt`. The VAE configuration declares
48 kHz stereo. This describes expected dependencies, not measured compatibility.

Only text Git objects, including LFS pointers, were read. For the four payloads
below, the identities and sizes are **published expectations**, not hashes
recalculated from acquired weights or latent bytes.

| Bundle path | Published SHA-256 | Published bytes |
|---|---|---:|
| `acestep-v15-turbo/model.safetensors` | `3f6e0797fad420a39bd33979eb6e840e30989e34a3794e843d23b60ec6e422d7` | 4787825604 |
| `acestep-v15-turbo/silence_latent.pt` | `a778e9dd942f5e8b2c09c55370782d318834432b03dabbcdf70e6ed49ad6358b` | 3841215 |
| `vae/diffusion_pytorch_model.safetensors` | `da17edb604c40deaf09e9b24974e590d1ca83a374070e5d0884cfa4bed9a99b0` | 337431388 |
| `Qwen3-Embedding-0.6B/model.safetensors` | `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd` | 1191586416 |

All paths belong to the [pinned ACE-Step bundle](https://huggingface.co/ACE-Step/Ace-Step1.5/tree/19671f406d603126926c1b7e2adc169acbcade22).
The encoder's LFS pointer is byte-identical to [Qwen's upstream pointer](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3/model.safetensors),
Git blob `9116264a405846ebfe4e95556b63b1ca07c892a0`. Its configuration is different:
the bundle declares `Qwen3Model`, while upstream declares `Qwen3ForCausalLM`.
Preserve the bundle's [configuration](https://huggingface.co/ACE-Step/Ace-Step1.5/blob/19671f406d603126926c1b7e2adc169acbcade22/Qwen3-Embedding-0.6B/config.json)
(Git blob `21bd712c76114dc22587c6eeb84ab64186c9d245`); pointer equality does not
justify substituting upstream configuration. Tokenizers and the complete runtime
dependency chain have not been independently qualified by this weight review.

## Two source findings that constrain the next adapter

In [generation](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/inference.py),
`thinking=False` alone is insufficient: caption, language or metadata CoT can
still request the LM. The preview must explicitly set `thinking`,
`use_cot_caption`, `use_cot_language`, `use_cot_metas` and `use_cot_lyrics` to false,
and declare that no planner LM will be initialized. These are proposed request
constraints; no live LM-bypass experiment was performed.

The [initialization precheck](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/init_service_downloads.py)
can download missing models and synchronize model-side Python files. The
[downloader](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/model_downloader.py)
requires the bundled 1.7B planner in its main-component presence check and invokes
snapshot downloads without a pinned `revision`, with cross-host fallback.
Consequently, disabling LM inference does not make stock initialization a
download-free or revision-pinned operation. A preview must never call it.

## Next bounded slice and remaining proof

Implement one pure request builder for a single 10-second instrumental
`text2music` request, batch size 1, with explicit seed, caption, all LM flags off
and the pinned source/component references above. This is a proposed test
envelope, not a quality recommendation or a hardware-fit claim.

The remaining proof for that slice is **a request preview that preserves those
parameters and references without any execution side effect**. Tests should
establish that it imports/initializes no provider, downloads nothing, makes no
network/process call or filesystem write, and returns `executed: false`,
`activation_allowed: false` and `review_required: true`. Published payload hashes
must remain labelled unverified. Invalid or out-of-profile input must be rejected
explicitly, with no silent clamping, rewriting, alternate model or fallback.

No adapter is implemented in this documentary slice. A later real-model
experiment would separately require acquired-artifact verification and a bounded
runtime/dependency setup. This review produces no music-quality, speedup,
Windows/GPU/homelab or output-rights proof. It adds no package installation,
checkpoint acquisition, model load, inference or rights-holder contact.
Atlas persistence, automatic routing, activation and merging remain out of scope;
the frozen Needle/Qwen comparison and its seed are unchanged.
