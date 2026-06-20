"""capabilities — the system's self-model: a capability registry + curator.

    from skills.capabilities.registry import load, ascii_map, curate
    print(ascii_map())                 # the layered arborescence
    curate("test my desktop app")      # pick relevant capabilities (local, 0 tokens)
"""

from skills.capabilities.registry import (
    load, by_layer, ascii_map, curate, Capability, LAYERS,
)

__all__ = ["load", "by_layer", "ascii_map", "curate", "Capability", "LAYERS"]
