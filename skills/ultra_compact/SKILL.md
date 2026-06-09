# Ultra-Compact JSON (P12)
Three compression levels: single-char keys, array format, delta-only.

**Trigger:** When generating JSON reports — always use the most compact format.

**Levels:**
1. Single-char keys: -30% vs standard compact
2. Array format (no keys): -38% vs compact
3. Delta-only (send changes): -90% for iterative reports

**Module:** `skills/ultra_compact`
**Functions:** to_ultra(), to_array(), delta_only(), compare_sizes()
